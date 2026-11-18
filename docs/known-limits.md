# Known limits

## Schema check

- The check proves a quote was said, not that it supports the value (e.g. "ank" can back "Barclays Bank"); the evaluation must catch this.
- Duplicate Turn.index values fail closed but can wrongly reject a good scammer quote; the session must keep indexes unique.
- check_dossier returns a shallow copy: the result shares objects with its input, so never mutate either in place.
- Rejections are returned, not logged; the caller (a later slice) must log them.
- Invisible characters (e.g. zero-width space) are not normalised, so "Mark from" does not match `"Ma\u200brk from"`.

## Cache

- Cache.load only checks the file parses; a wrong shape (list, number, null, `{}`), an empty/truncated/BOM file, or a mismatched stored provider/method raises an unhelpful error (TypeError/KeyError/JSONDecodeError), and in record mode a corrupt file is not re-recorded, it must be deleted by hand.
- Writes are not atomic: a crash mid-write leaves a truncated file. Reads and writes follow symlinks.
- The key has no prompt or model version, so after a prompt change replay serves stale replies; a real provider must put its version in `name`.
