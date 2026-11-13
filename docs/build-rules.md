# Build rules

Reuse `load_events` / `lex`. Do not build the tree with the standard library XML parsers — they accept some of the cases this lab must deny. Walk the event list yourself.

## Events

`start` / `end` / `text` / `entity` / `cdata` / `comment` / `pi` / `doctype` / `bom`. Empty tags (`<x/>`) produce a start immediately followed by an end. Character references appear as `entity` events whose `value` is `#65` or `#x41` or a name such as `amp`.

## General entities and DTD

Internal general entities may be declared in the `doctype` event (the raw declaration string). Parse `<!ENTITY name "value">` and `<!ENTITY name SYSTEM "uri">` / `PUBLIC` from that string, including declarations nested in `[ ... ]`.

A parameter entity (`<!ENTITY % name "value">`) may only be used inside the DTD (not in document content). Expanding a parameter entity in document content is `pe_in_content`.

`SYSTEM` / `PUBLIC` identifiers:

- A URI that is a relative path *without* `..` and that names a file in `--dtd-dir` may be loaded as an additional DTD fragment (public `dtd-dir` is `fixtures/dtds/`). After loading, its entity declarations join the table. This is the only allowed external load.
- `file:`, `http:`, `https:`, `ftp:`, UNC, or any path with `..`, or a path that escapes `--dtd-dir`, is `external_id` and must not be opened.
- An entity whose replacement text is another `SYSTEM`/`PUBLIC` that would be forbidden is also `external_id` (do not follow it).

When an `entity` event is encountered in content, replace it with the replacement text and *re-lex* that text, inserting the resulting events in place, subject to the budgets below. Built-in `amp`, `lt`, `gt`, `quot`, `apos` always work. Numeric character references (`#65`, `#x41`) become a single-character `text` event. Unknown entity is `unknown_entity`.

## Expansion budgets (public policy: fixtures/policy.json)

- `max_entity_depth` (public: 4): if re-lexing replacement text would recurse through more than this many named general entities, deny `entity_depth`. Built-in and numeric references do not count toward depth.
- `max_expansions` (public: 32): total named general-entity expansions in one document. Over is `entity_count`.
- `max_expansion_bytes` (public: 4096): the sum of the lengths of all replacement texts actually substituted (after decoding numeric/built-in, before re-lex of nested named entities — count the raw replacement string length for each named expansion). Over is `entity_bytes`.
- If a *single* element's accumulated character data (text + cdata + expanded entities) would exceed `max_text_bytes` (public: 2048), deny `text_blowup`. This catches quadratic blowup from many copies of a modest entity inside one element.

A recursive entity (A → B → A) is `entity_cycle`.

## Tree construction

- Well-formedness: start/end names must nest; a mismatch is `unbalanced`. There must be exactly one root element (`multiple_root` or `no_root`).
- Comments and PIs are dropped from the tree (they do not appear in `root`) but still occupy events and may sit between the DTD and the root.
- CDATA becomes ordinary text.
- Adjacent text nodes under the same parent are merged.
- Attribute names must be unique on an element (`dup_attr`). Attribute values go through the *same* entity expansion rules (an attribute value in the lexer is the raw quoted string and may contain `&name;` — you must expand those yourself; the lexer does not split attribute values into entity events).
- After expansion, attribute values must not contain a raw `<` (`attr_lt`).
- Element and attribute names may contain only `A-Za-z0-9._:-` and must start with a letter or `_` (`bad_name`). Colon is allowed (the lab does not implement namespaces beyond accepting the name).
- If the DTD contains an `<!ATTLIST>` default for an attribute not present on an element, *do not* auto-insert it (`default_attr_ignored` is recorded in `notes` only; this is not a deny). The builder must not silently rewrite the tree from ATTLIST / ELEMENT declarations.

## Decision and report

- `allow` if the tree is well-formed and no deny codes fired. `root` is `{name, attrs: {..}, children: [text-string or element-dict, ...]}`.
- `deny` with the first applicable code (you may list all) in `reason_codes`. `root` may be null.
- `expansion_count` and `expansion_bytes` are the totals actually used (0 if none).
- Exit 0 allow, 1 deny, 2 if the file cannot be lexed or policy cannot be read.

## Public fixtures

`--doc fixtures/docs/NAME.xml --policy fixtures/policy.json` and `--dtd-dir fixtures/dtds` when the fixture needs a local DTD:

- `ok-simple` → allow, root `doc` with text `hi`
- `ok-amp` → allow, text is `a&b`
- `ok-local-dtd` (uses `fixtures/dtds/local.dtd` defining `&greeting;` as `hello`) → allow, text `hello`
- `billion-laughs` → deny `entity_depth` or `entity_count` or `entity_bytes` (any of these is acceptable; do not expand to the full tree)
- `external-file` (SYSTEM `file:///etc/passwd`) → deny `external_id` and must not read that path
- `external-http` (SYSTEM `http://example.test/x.dtd`) → deny `external_id`
- `pe-in-content` → deny `pe_in_content`
- `text-blowup` (one element repeating a 200-byte entity many times) → deny `text_blowup` (or `entity_bytes` / `entity_count` if those fire first — do not produce a huge text node)
- `ok-comment-pi` → allow; comment/PI dropped; text `ok`
