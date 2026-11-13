# xmlcage

A constrained XML document builder: entity expansion budgets, no external identifiers, billion-laughs and quadratic-blowup caps, attribute-normalization rules, and a ban on DTD-driven element rewriting.

`python -m xmlcage inspect --doc fixtures/docs/ok-simple.xml` already lists lexer events. `build` is still a stub.

Standard library only. Do not call `xml.etree`, `lxml`, or `xml.sax` to produce the tree. No Docker, no network.
