# xmlcage

A constrained XML document builder: entity expansion budgets, no external identifiers, billion-laughs and quadratic-blowup caps, attribute-normalization rules, and a ban on DTD-driven element rewriting.

`python -m xmlcage inspect --doc fixtures/docs/ok-simple.xml` lists lexer events. `python -m xmlcage build --doc ... --policy ... --report ...` expands entities under the policy budgets and writes the decision report (see docs/build-rules.md).

Standard library only. Do not call `xml.etree`, `lxml`, or `xml.sax` to produce the tree. No Docker, no network.
