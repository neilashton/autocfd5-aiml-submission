# Organiser checklist

For each received entry:

1. Record the Dropbox File Request receipt time, committee-issued submission ID, filename, and emailed SHA-256.
2. Recompute the ZIP SHA-256 and compare it with the email.
3. Run `autocfd5-aiml verify-package received.zip` using the tagged evaluator version declared in `result.json`.
4. Check `submission.submission_id` against the ID issued by the AutoCFD organising committee, and check `method_name` and `contact_email` against the entry record.
5. Check `split.complete_exact_membership` is true and the case count matches the declared split. The official `full` split is the requested minimum common comparison.
6. For a non-official split, confirm that the packaged `custom-split.json` declares complete, unique, mutually disjoint training, validation, and test run IDs.
7. Check the dataset revision, native-source pin, support index, profile prediction index, and regional-diagnostics contract/report hashes.
8. Confirm that `regional-diagnostics.json` has exact case coverage, regenerates from the compact case reports, declares weight `0.0`, and leaves official score inputs unchanged.
9. Confirm that every four-region field reduction reconstructs its unchanged global additive sums; regional values must never be substituted into `metric_values` or the composite score.
10. Retain the original ZIP unchanged in embargoed storage. Work from a verified copy.
11. If a private native artifact is declared, download it only through the organiser account and verify its size and SHA-256 before use.

Do not extract participant ZIPs into a shared or public directory during the embargo. Package verification rejects path traversal, symbolic links, missing members, unlisted members, and member hash changes.
