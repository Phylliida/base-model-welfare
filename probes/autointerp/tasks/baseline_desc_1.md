# Descriptions of the directions

### D19
Label: chatty vs institutional
High values: in chatty first- and second-person text, away from names and at sentence or line ends. In ordinary text it is high in chatty first- and second-person text, away from names and at sentence or line ends (r with |h| divided out: I/you/! +0.33, names −0.23, sentence end +0.20).
Low values: in impersonal text, inside names and mid-clause
Pushed toward HIGH, the model writes: writes more you ‹doc-end› it we I; less ␣ , and women R
Pushed toward LOW, the model writes: writes more ␣ , and women R; less you ‹doc-end› it we I
Items to answer: 12 detection pairs, 12 intervention pairs

### D20
Label: sentence position
High values: deep into sentences, mid-clause and where function words are dense. In ordinary text it is high deep into sentences, mid-clause and where function words are dense (r with |h| divided out: tokens since sentence end +0.36, sentence end −0.23, function words +0.16), rising steadily through a sentence.
Low values: near sentence ends, at sentence or line ends and where function words are sparse
Pushed toward HIGH, the model writes: writes more .⏎ ‹doc-end› .; less and as that in when
Pushed toward LOW, the model writes: writes more and as that in when; less .⏎ ‹doc-end› .
Items to answer: 12 detection pairs, 12 intervention pairs

### D21
Label: chatty vs institutional
High values: in chatty first- and second-person text and away from names. In ordinary text it is high in chatty first- and second-person text and away from names (r with |h| divided out: I/you/! +0.32, names −0.19).
Low values: in impersonal text and inside names
Pushed toward HIGH, the model writes: writes more it I ! you look; less and research of , Center
Pushed toward LOW, the model writes: writes more and research of , Center; less it I ! you look
Items to answer: 12 detection pairs, 12 intervention pairs

### D22
Label: prose vs structured text
High values: where function words are sparse, in structured text (newlines, digits, symbols) and inside names. In ordinary text it is high where function words are sparse, in structured text (newlines, digits, symbols) and inside names (r with |h| divided out: function words −0.38, markup +0.38, names +0.25).
Low values: where function words are dense, in running prose and away from names
Pushed toward HIGH, the model writes: writes more ‹doc-end› ⏎ ␣ !⏎ 1; less the of that as are
Pushed toward LOW, the model writes: writes more the of that as are; less ‹doc-end› ⏎ ␣ !⏎ 1
Items to answer: 12 detection pairs, 12 intervention pairs

### D23
Label: sentence position
High values: deep into sentences, mid-clause and in running prose. In ordinary text it is high deep into sentences, mid-clause and in running prose (r with |h| divided out: tokens since sentence end +0.49, sentence end −0.31, markup −0.23), rising steadily through a sentence.
Low values: near sentence ends, at sentence or line ends and in structured text (newlines, digits, symbols)
Pushed toward HIGH, the model writes: writes more ‹doc-end› .⏎ ⏎; less , and the of who
Pushed toward LOW, the model writes: writes more , and the of who; less ‹doc-end› .⏎ ⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D24
Label: proper names
High values: inside names, deep into sentences and in impersonal text. In ordinary text it is high inside names, deep into sentences and in impersonal text (r with |h| divided out: names +0.25, tokens since sentence end +0.23, I/you/! −0.18).
Low values: away from names, near sentence ends and in chatty first- and second-person text
Pushed toward HIGH, the model writes: writes more . ‹doc-end› .⏎ I look; less man , ; across or
Pushed toward LOW, the model writes: writes more man , ; across or; less . ‹doc-end› .⏎ I look
Items to answer: 12 detection pairs, 12 intervention pairs

### D25
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and inside names. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and inside names (r with |h| divided out: markup +0.39, function words −0.31, names +0.22).
Low values: in running prose, where function words are dense and away from names
Pushed toward HIGH, the model writes: writes more ‹doc-end› & : ⏎; less the a is that are
Pushed toward LOW, the model writes: writes more the a is that are; less ‹doc-end› & : ⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D26
Label: proper names
High values: inside names, where the next token is predictable and in impersonal text. In ordinary text it is high inside names, where the next token is predictable and in impersonal text (r with |h| divided out: names +0.30, entropy −0.28, I/you/! −0.22).
Low values: away from names, where the next token is uncertain and in chatty first- and second-person text
Pushed toward HIGH, the model writes: writes more it that just you they; less from National New the of
Pushed toward LOW, the model writes: writes more from National New the of; less it that just you they
Items to answer: 12 detection pairs, 12 intervention pairs

### D27
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and inside names. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and inside names (r with |h| divided out: markup +0.40, function words −0.34, names +0.28).
Low values: in running prose, where function words are dense and away from names
Pushed toward HIGH, the model writes: writes more ␣ ‹doc-end› ⏎ 1 ⏎⏎; less that to they it are
Pushed toward LOW, the model writes: writes more that to they it are; less ␣ ‹doc-end› ⏎ 1 ⏎⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D28
Label: proper names
High values: inside names, where function words are sparse and in structured text (newlines, digits, symbols). In ordinary text it is high inside names, where function words are sparse and in structured text (newlines, digits, symbols) (r with |h| divided out: names +0.30, function words −0.26, markup +0.24).
Low values: away from names, where function words are dense and in running prose
Pushed toward HIGH, the model writes: writes more that you we and more; less ␣ .⏎ ⏎⏎ National el
Pushed toward LOW, the model writes: writes more ␣ .⏎ ⏎⏎ National el; less that you we and more
Items to answer: 12 detection pairs, 12 intervention pairs

### D29
Label: prose vs structured text
High values: in structured text (newlines, digits, symbols), where function words are sparse and at sentence or line ends. In ordinary text it is high in structured text (newlines, digits, symbols), where function words are sparse and at sentence or line ends (r with |h| divided out: markup +0.40, function words −0.36, sentence end +0.24).
Low values: in running prose, where function words are dense and mid-clause
Pushed toward HIGH, the model writes: writes more ‹doc-end› ⏎ ␣ : !⏎; less and the that to of
Pushed toward LOW, the model writes: writes more and the that to of; less ‹doc-end› ⏎ ␣ : !⏎
Items to answer: 12 detection pairs, 12 intervention pairs

### D30
Label: chatty vs institutional
High values: in chatty first- and second-person text, at sentence or line ends and away from names. In ordinary text it is high in chatty first- and second-person text, at sentence or line ends and away from names (r with |h| divided out: I/you/! +0.34, sentence end +0.19, names −0.19).
Low values: in impersonal text, mid-clause and inside names
Pushed toward HIGH, the model writes: writes more you it I ! just; less and of research the University
Pushed toward LOW, the model writes: writes more and of research the University; less you it I ! just
Items to answer: 12 detection pairs, 12 intervention pairs

### D31
Label: break vs continue
High values: at sentence or line ends, where function words are sparse and near sentence ends. In ordinary text it is high at sentence or line ends, where function words are sparse and near sentence ends (r with |h| divided out: sentence end +0.29, function words −0.22, tokens since sentence end −0.21), a spike at the token itself rather than a running count.
Low values: mid-clause, where function words are dense and deep into sentences
Pushed toward HIGH, the model writes: writes more ‹doc-end› ⏎ 1; less the well in as with
Pushed toward LOW, the model writes: writes more the well in as with; less ‹doc-end› ⏎ 1
Items to answer: 12 detection pairs, 12 intervention pairs

### D32
Label: chatty vs institutional
High values: in chatty first- and second-person text and away from names. In ordinary text it is high in chatty first- and second-person text and away from names (r with |h| divided out: I/you/! +0.36, names −0.24).
Low values: in impersonal text and inside names
Pushed toward HIGH, the model writes: writes more it you ‹doc-end› just !; less and research by Center of
Pushed toward LOW, the model writes: writes more and research by Center of; less it you ‹doc-end› just !
Items to answer: 12 detection pairs, 12 intervention pairs

### D33
Label: break vs continue
High values: at sentence or line ends, in structured text (newlines, digits, symbols) and where function words are sparse. In ordinary text it is high at sentence or line ends, in structured text (newlines, digits, symbols) and where function words are sparse (r with |h| divided out: sentence end +0.34, markup +0.27, function words −0.23), a spike at the token itself rather than a running count.
Low values: mid-clause, in running prose and where function words are dense
Pushed toward HIGH, the model writes: writes more the a it is to; less ‹doc-end› ) ⏎ (
Pushed toward LOW, the model writes: writes more ‹doc-end› ) ⏎ (; less the a it is to
Items to answer: 12 detection pairs, 12 intervention pairs

### D34
Label: predictability
High values: where the next token is uncertain, in running prose and where function words are dense. In ordinary text it is high where the next token is uncertain, in running prose and where function words are dense (r with |h| divided out: entropy +0.41, markup −0.23, function words +0.21).
Low values: where the next token is predictable, in structured text (newlines, digits, symbols) and where function words are sparse
Pushed toward HIGH, the model writes: writes more the of in after against; less I . ␣ , -
Pushed toward LOW, the model writes: writes more I . ␣ , -; less the of in after against
Items to answer: 12 detection pairs, 12 intervention pairs

### D35
Label: unidentified
High values: where the next token is uncertain, where function words are dense and in running prose. In ordinary text it is high where the next token is uncertain, where function words are dense and in running prose (r with |h| divided out: entropy +0.24, function words +0.17, markup −0.16).
Low values: where the next token is predictable, where function words are sparse and in structured text (newlines, digits, symbols)
Pushed toward HIGH, the model writes: writes more ‹doc-end› /; less . I was it a
Pushed toward LOW, the model writes: writes more . I was it a; less ‹doc-end› /
Items to answer: 12 detection pairs, 12 intervention pairs

### D36
Label: unidentified
High values: right after expected tokens and deep into sentences. In ordinary text it is high right after expected tokens and deep into sentences (r with |h| divided out: surprisal −0.23, tokens since sentence end +0.22).
Low values: right after surprising tokens and near sentence ends
Pushed toward HIGH, the model writes: writes more ‹doc-end› .⏎ ⏎ .<; less , and the or ’m
Pushed toward LOW, the model writes: writes more , and the or ’m; less ‹doc-end› .⏎ ⏎ .<
Items to answer: 12 detection pairs, 12 intervention pairs
