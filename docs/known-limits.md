# Known limits (schema check)

- The check proves a quote was said, not that it supports the value (e.g. "ank" can back "Barclays Bank"); the evaluation must catch this.
- Duplicate Turn.index values fail closed but can wrongly reject a good scammer quote; the session must keep indexes unique.
- check_dossier returns a shallow copy: the result shares objects with its input, so never mutate either in place.
- Rejections are returned, not logged; the caller (a later slice) must log them.
- Invisible characters (e.g. zero-width space) are not normalised, so "Mark from" does not match `"Ma\u200brk from"`.
