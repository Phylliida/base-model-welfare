# Descriptions of the directions

### D01
Label: proper names
High values: where the next token is predictable, inside names and in structured text (newlines, digits, symbols). In ordinary text it is high where the next token is predictable, inside names and in structured text (newlines, digits, symbols) (r with |h| divided out: entropy −0.35, names +0.32, markup +0.27).
Low values: where the next token is uncertain, away from names and in running prose
Pushed toward HIGH, the model writes: writes more and it but that are; less .⏎ th ‹doc-end› The service
Pushed toward LOW, the model writes: writes more .⏎ th ‹doc-end› The service; less and it but that are
Items to answer: 12 detection pairs, 12 intervention pairs

### D02
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and inside names. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and inside names (r with |h| divided out: markup +0.42, function words −0.37, names +0.27).
Low values: in running prose, where function words are dense and away from names
Pushed toward HIGH, the model writes: writes more ␣ ‹doc-end› ⏎ / 3; less are that to the it
Pushed toward LOW, the model writes: writes more are that to the it; less ␣ ‹doc-end› ⏎ / 3
Items to answer: 12 detection pairs, 12 intervention pairs

### D03
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and inside names. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and inside names (r with |h| divided out: markup +0.41, function words −0.38, names +0.24).
Low values: in running prose, where function words are dense and away from names
Pushed toward HIGH, the model writes: writes more ␣ ‹doc-end› ⏎ !⏎ :; less the and to that are
Pushed toward LOW, the model writes: writes more the and to that are; less ␣ ‹doc-end› ⏎ !⏎ :
Items to answer: 12 detection pairs, 12 intervention pairs

### D04
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and inside names. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and inside names (r with |h| divided out: markup +0.42, function words −0.35, names +0.24).
Low values: in running prose, where function words are dense and away from names
Pushed toward HIGH, the model writes: writes more ␣ ‹doc-end› ⏎ & /; less the that is to are
Pushed toward LOW, the model writes: writes more the that is to are; less ␣ ‹doc-end› ⏎ & /
Items to answer: 12 detection pairs, 12 intervention pairs

### D05
Label: sentence position
High values: deep into sentences, inside names and where the next token is predictable. In ordinary text it is high deep into sentences, inside names and where the next token is predictable (r with |h| divided out: tokens since sentence end +0.31, names +0.21, entropy −0.20), rising steadily through a sentence.
Low values: near sentence ends, away from names and where the next token is uncertain
Pushed toward HIGH, the model writes: writes more ‹doc-end› . you look; less M of from Center ,
Pushed toward LOW, the model writes: writes more M of from Center ,; less ‹doc-end› . you look
Items to answer: 12 detection pairs, 12 intervention pairs

### D06
Label: sentence position
High values: deep into sentences, in running prose and where function words are dense. In ordinary text it is high deep into sentences, in running prose and where function words are dense (r with |h| divided out: tokens since sentence end +0.46, markup −0.25, function words +0.25), rising steadily through a sentence.
Low values: near sentence ends, in structured text (newlines, digits, symbols) and where function words are sparse
Pushed toward HIGH, the model writes: writes more .⏎ ‹doc-end› ⏎ The :⏎; less the , as that and
Pushed toward LOW, the model writes: writes more the , as that and; less .⏎ ‹doc-end› ⏎ The :⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D07
Label: chatty vs institutional
High values: in chatty first- and second-person text and away from names. In ordinary text it is high in chatty first- and second-person text and away from names (r with |h| divided out: I/you/! +0.36, names −0.27).
Low values: in impersonal text and inside names
Pushed toward HIGH, the model writes: writes more it ‹doc-end› I you !; less and M research , The
Pushed toward LOW, the model writes: writes more and M research , The; less it ‹doc-end› I you !
Items to answer: 12 detection pairs, 12 intervention pairs

### D08
Label: sentence position
High values: deep into sentences, mid-clause and in running prose. In ordinary text it is high deep into sentences, mid-clause and in running prose (r with |h| divided out: tokens since sentence end +0.49, sentence end −0.27, markup −0.27), rising steadily through a sentence.
Low values: near sentence ends, at sentence or line ends and in structured text (newlines, digits, symbols)
Pushed toward HIGH, the model writes: writes more ‹doc-end› .⏎ ⏎ .; less , the and to or
Pushed toward LOW, the model writes: writes more , the and to or; less ‹doc-end› .⏎ ⏎ .
Items to answer: 12 detection pairs, 12 intervention pairs

### D09
Label: chatty vs institutional
High values: in chatty first- and second-person text. In ordinary text it is high in chatty first- and second-person text (r with |h| divided out: I/you/! +0.30).
Low values: in impersonal text
Pushed toward HIGH, the model writes: writes more I ! there 't about; less include , of research op
Pushed toward LOW, the model writes: writes more include , of research op; less I ! there 't about
Items to answer: 12 detection pairs, 12 intervention pairs

### D10
Label: unidentified
High values: where the next token is predictable, at sentence or line ends and right after expected tokens. In ordinary text it is high where the next token is predictable, at sentence or line ends and right after expected tokens (r with |h| divided out: entropy −0.22, sentence end +0.17, surprisal −0.16).
Low values: where the next token is uncertain, mid-clause and right after surprising tokens
Pushed toward HIGH, the model writes: writes more the a of The in; less I to ’t not or
Pushed toward LOW, the model writes: writes more I to ’t not or; less the a of The in
Items to answer: 12 detection pairs, 12 intervention pairs

### D11
Label: break vs continue
High values: in structured text (newlines, digits, symbols), at sentence or line ends and where function words are sparse. In ordinary text it is high in structured text (newlines, digits, symbols), at sentence or line ends and where function words are sparse (r with |h| divided out: markup +0.35, sentence end +0.33, function words −0.29), a spike at the token itself rather than a running count.
Low values: in running prose, mid-clause and where function words are dense
Pushed toward HIGH, the model writes: writes more ‹doc-end› ) : ( &; less the a is that it
Pushed toward LOW, the model writes: writes more the a is that it; less ‹doc-end› ) : ( &
Items to answer: 12 detection pairs, 12 intervention pairs

### D12
Label: predictability
High values: where the next token is uncertain, at sentence or line ends and in chatty first- and second-person text. In ordinary text it is high where the next token is uncertain, at sentence or line ends and in chatty first- and second-person text (r with |h| divided out: entropy +0.47, sentence end +0.26, I/you/! +0.21).
Low values: where the next token is predictable, mid-clause and in impersonal text
Pushed toward HIGH, the model writes: writes more in ‹doc-end› you make what; less , the ; / ley
Pushed toward LOW, the model writes: writes more , the ; / ley; less in ‹doc-end› you make what
Items to answer: 12 detection pairs, 12 intervention pairs

### D13
Label: chatty vs institutional
High values: in chatty first- and second-person text, near sentence ends and at sentence or line ends. In ordinary text it is high in chatty first- and second-person text, near sentence ends and at sentence or line ends (r with |h| divided out: I/you/! +0.27, tokens since sentence end −0.17, sentence end +0.17).
Low values: in impersonal text, deep into sentences and mid-clause
Pushed toward HIGH, the model writes: writes more it ‹doc-end› I just you; less and research of the for
Pushed toward LOW, the model writes: writes more and research of the for; less it ‹doc-end› I just you
Items to answer: 12 detection pairs, 12 intervention pairs

### D14
Label: proper names
High values: inside names, in impersonal text and where the next token is predictable. In ordinary text it is high inside names, in impersonal text and where the next token is predictable (r with |h| divided out: names +0.25, I/you/! −0.21, entropy −0.19).
Low values: away from names, in chatty first- and second-person text and where the next token is uncertain
Pushed toward HIGH, the model writes: writes more to ‹doc-end› more just that; less Center by National : el
Pushed toward LOW, the model writes: writes more Center by National : el; less to ‹doc-end› more just that
Items to answer: 12 detection pairs, 12 intervention pairs

### D15
Label: sentence position
High values: deep into sentences, mid-clause and in running prose. In ordinary text it is high deep into sentences, mid-clause and in running prose (r with |h| divided out: tokens since sentence end +0.52, sentence end −0.24, markup −0.23), rising steadily through a sentence.
Low values: near sentence ends, at sentence or line ends and in structured text (newlines, digits, symbols)
Pushed toward HIGH, the model writes: writes more ‹doc-end› .⏎ . ⏎; less , the to of or
Pushed toward LOW, the model writes: writes more , the to of or; less ‹doc-end› .⏎ . ⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D16
Label: sentence position
High values: deep into sentences, where the next token is predictable and mid-clause. In ordinary text it is high deep into sentences, where the next token is predictable and mid-clause (r with |h| divided out: tokens since sentence end +0.50, entropy −0.33, sentence end −0.32), rising steadily through a sentence.
Low values: near sentence ends, where the next token is uncertain and at sentence or line ends
Pushed toward HIGH, the model writes: writes more ‹doc-end› .⏎ . ⏎; less , the and of or
Pushed toward LOW, the model writes: writes more , the and of or; less ‹doc-end› .⏎ . ⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D17
Label: predictability
High values: where the next token is uncertain, in running prose and at sentence or line ends. In ordinary text it is high where the next token is uncertain, in running prose and at sentence or line ends (r with |h| divided out: entropy +0.42, markup −0.18, sentence end +0.18).
Low values: where the next token is predictable, in structured text (newlines, digits, symbols) and mid-clause
Pushed toward HIGH, the model writes: writes more in of this make through; less ␣ I , / ;
Pushed toward LOW, the model writes: writes more ␣ I , / ;; less in of this make through
Items to answer: 12 detection pairs, 12 intervention pairs

### D18
Label: unidentified
High values: where the next token is uncertain, near sentence ends and at sentence or line ends. In ordinary text it is high where the next token is uncertain, near sentence ends and at sentence or line ends (r with |h| divided out: entropy +0.22, tokens since sentence end −0.20, sentence end +0.18).
Low values: where the next token is predictable, deep into sentences and mid-clause
Pushed toward HIGH, the model writes: writes more !⏎ look worth 1 it; less looks ing / and members
Pushed toward LOW, the model writes: writes more looks ing / and members; less !⏎ look worth 1 it
Items to answer: 12 detection pairs, 12 intervention pairs
