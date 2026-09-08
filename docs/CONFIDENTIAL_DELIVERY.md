# Confidential delivery

Entries remain confidential during the workshop embargo. The GitHub repository distributes evaluator code, documentation, examples, and immutable support only; it is not an entry drop box.

1. Run the evaluator locally on the complete selected test split.
2. Inspect `result.json` and selected case reports.
3. Run `autocfd5-aiml package ...` to create one deterministic ZIP and its `.sha256` file for each split you submit.
4. Run `autocfd5-aiml verify-package ...` on that ZIP.
5. Use the same committee-issued submission ID in every entry. Name the required `full`-split ZIP `submission-id.zip`; name each additional official-split ZIP `submission-id--<split-id>.zip`.
6. Upload each ZIP using the [AutoCFD Dropbox File Request](https://www.dropbox.com/request/A6cJNTT9egFtYiFICjAi).
7. Email the organisers the submission ID, split ID, submitted filename, and SHA-256. The email is a receipt notice, not the file transport.

Do not commit an entry, attach it to an issue, or open a pull request with it. Organisers should restrict the Dropbox File Request destination to the small processing group until the embargo ends.

The standard ZIP includes the declared training regime and pretraining sources, prediction scope and force route, compact metrics and component availability, field-integrated forces, any direct-force input files and identities, available profile predictions, explicit unavailable velocity-profile rows for surface-only entries, and the zero-weight `regional-diagnostics.json` report. It does not include the large native prediction chunks. If organisers require those large artifacts, place them in private immutable storage and declare `prediction_artifact.private_immutable_url`, `size_bytes`, and `sha256` in `entry.json`. The evaluator records that reference but does not copy the large artifact into the ZIP.

Organiser acknowledgements should state the received filename and SHA-256, without circulating results.

Questions can be sent to `neil@neilashton.co.uk` or `astridwalle@cfdsolutions.net`, the AutoCFD5 AI/ML TFG organisers.
