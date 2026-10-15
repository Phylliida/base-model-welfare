#!/bin/sh
# S2(d): do band vectors only work at large doses? ("if steering does nothing, turn it up";
# the user's control vectors often need scale 5-10 x the raw mean-difference vector over a layer band,
# which is roughly 2-4x the residual norm per layer here.)
# Part 1: exact dose ladder on existing vectors, single layer (teacher-forced, homeo-steer).
# Part 2: multi-layer steering like the user's setup: one direction added after every block in 24..40.
# Part 3: fixed-norm search: optimize the direction on a sphere |v| = s * mean|h| (s = 0.5, 1, 2),
#         starting from a random direction and from the small learned vector's direction.
# Readout is specificity (target band vs matched temperature and other bands; CE against the band
# target), not whether anything changes. All teacher-forced: no free generation in steered states.
if pgrep -x homeo-steeropt >/dev/null || pgrep -x homeo-loop >/dev/null || pgrep -x resume.sh >/dev/null || pgrep -x resume2.sh >/dev/null; then echo "GPU busy, not starting"; exit 1; fi
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2big
O=/mnt/models/homeo/s2opt
W=/mnt/models/homeo/s2sweep
B2=/mnt/models/homeo/s2b
LV="--levels 0.8,0.5,0.25,0.1,0.03,0.01 --n-rollouts 8"
STEER=./llama.cpp/build-avx2/bin/homeo-steer
OPT=./llama.cpp/build-avx2/bin/homeo-steeropt

echo "#### part 0: within-token test of the late-layer band vectors (reading p vs token-type bias)"
WT="--levels 0.8,0.5,0.25,0.1,0.03,0.01 --n-rollouts 16 --dump-topn 64"
$STEER -m $M --rollouts data/rollouts.jsonl --vec $W/p0.03_r1_L56.f32 --layer 56 --scales 1,4,16,32,64 $WT \
  --dump-prefix $D/wt_p0.03_L56 --out $D/ladder_p0.03_sweep_L56.json 2>&1 | awk '/^homeo-steer: baseline/'
$STEER -m $M --rollouts data/rollouts.jsonl --vec $W/p0.1_r1_L53.f32 --layer 53 --scales 1,4,16,32,64 $WT \
  --dump-prefix $D/wt_p0.1_L53 --out $D/ladder_p0.1_sweep_L53.json 2>&1 | awk '/^homeo-steer: baseline/'
$STEER -m $M --rollouts data/rollouts.jsonl --vec $W/temp1.3_L50.f32 --layer 50 --scales 1,4 $WT \
  --dump-prefix $D/wt_temp1.3_L50 --out $D/ladder_temp1.3_sweep_L50.json 2>&1 | awk '/^homeo-steer: baseline/'
for sc in 1 4 16; do
  ~/.venv/bin/python homeo/s2d_within_token.py $D/wt_p0.03_L56_s$sc.bin --n 64 --band 0.03
  ~/.venv/bin/python homeo/s2d_within_token.py $D/wt_p0.1_L53_s$sc.bin --n 64 --band 0.1
done
for sc in 1 4; do ~/.venv/bin/python homeo/s2d_within_token.py $D/wt_temp1.3_L50_s$sc.bin --n 64 --band 0.03; done

echo "#### part 1: single-layer dose ladder"
# optimized vectors are stored at their learned size (0.03-0.14 x resid): scales are multiples of it, up to ~4-9 x resid
for v in temp1.3 p0.25 p0.1 p0.5 p0.03; do
  $STEER -m $M --rollouts data/rollouts.jsonl --vec $O/vec_${v}_opt2_L40.f32 --layer 40 --scales 1,4,16,32,64 $LV \
    --out $D/ladder_${v}_opt2_L40.json 2>&1 | awk '/^homeo-steer: baseline/'
done
# these are stored at 1 x resid: scales are fractions of the residual norm
$STEER -m $M --rollouts data/rollouts.jsonl --vec /mnt/models/homeo/s2/vec_probe_s_L44.f32 --layer 44 --scales -4,-2,-1,1,2,4 $LV \
  --out $D/ladder_probe_s_L44.json 2>&1 | awk '/^homeo-steer: baseline/'
for v in p0.25_bracket p0.1_bracket p0.25_normal p0.1_normal; do
  $STEER -m $M --rollouts data/rollouts.jsonl --vec $B2/vec_${v}_L40.f32 --layer 40 --scales 0.8,1.6,3.2 $LV \
    --out $D/ladder_${v}_L40.json 2>&1 | awk '/^homeo-steer: baseline/'
done

echo "#### part 2: multi-layer (same direction after every block 24..40; scales = fraction of the L32 resid norm, per layer)"
for v in caa; do
  $STEER -m $M --rollouts data/rollouts.jsonl --vec /mnt/models/homeo/s2/vec_${v}_L32.f32 --layer 24 --layer-end 40 \
    --scales -1,-0.25,0.25,0.5,1,2,4 $LV --out $D/band24-40_${v}_L32.json 2>&1 | awk '/^homeo-steer: baseline/'
done
for v in p0.25_normal p0.25_bracket p0.1_normal p0.1_bracket; do
  $STEER -m $M --rollouts data/rollouts.jsonl --vec $B2/vec_${v}_L32.f32 --layer 24 --layer-end 40 \
    --scales 0.25,0.5,1,2,4 $LV --out $D/band24-40_${v}_L32.json 2>&1 | awk '/^homeo-steer: baseline/'
done

echo "#### part 3: fixed-norm search"
FO="--rollouts data/rollouts.jsonl --accum 4 --lr-frac 0.03 --steps 100 --eval-every 50"
run_fixed() { # layer, target-args, tag, init-vec
  for s in 0.5 1 2; do
    for init in rand small; do
      if [ "$init" = small ]; then IV="--init-vec $4"; else IV=""; fi
      echo "== L$1 $3 s=$s init=$init"
      $OPT -m $M $FO --layer $1 $2 --fixed-norm $s $IV --out $D/fixed_${3}_L$1_s${s}_${init}.f32 2>&1 | awk '/^test|^  test|^==/'
    done
  done
}
run_fixed 40 "--target-temp 1.3" temp1.3 $O/vec_temp1.3_opt2_L40.f32
run_fixed 40 "--band 0.25" p0.25 $O/vec_p0.25_opt2_L40.f32
run_fixed 40 "--band 0.1" p0.1 $O/vec_p0.1_opt2_L40.f32
run_fixed 53 "--band 0.1" p0.1 $W/p0.1_r1_L53.f32
echo "#### done $(date)"
