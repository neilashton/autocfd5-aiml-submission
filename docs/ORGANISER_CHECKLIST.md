# Organizer checklist

For each received entry:

1. Record the File Request receipt time, team ID, filename, and emailed SHA-256.
2. Recompute the ZIP SHA-256 and compare it with the email.
3. Run `autocfd5-aiml verify-package received.zip` using the tagged evaluator version declared in `result.json`.
4. Check `submission.submission_id`, `team_id`, and `method_name` against registration records.
5. Check `split.complete_exact_membership` is true and the case count matches the declared split.
6. Check the dataset revision, native-source pin, support index, and profile prediction index hashes.
7. Retain the original ZIP unchanged in embargoed storage. Work from a verified copy.
8. If a private native artifact is declared, download it only through the organizer account and verify its size and SHA-256 before use.

Do not extract participant ZIPs into a shared or public directory during the embargo. Package verification rejects path traversal, symbolic links, missing members, unlisted members, and member hash changes.
