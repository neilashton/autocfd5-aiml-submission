# Confidential delivery

Entries remain confidential during the workshop embargo. The GitHub repository distributes evaluator code, documentation, examples, and immutable support only; it is not an entry drop box.

1. Run the evaluator locally on the complete selected test split.
2. Inspect `result.json` and selected case reports.
3. Run `autocfd5-aiml package ...` to create one deterministic ZIP and its `.sha256` file.
4. Run `autocfd5-aiml verify-package ...` on that ZIP.
5. Upload only the ZIP using the organizer-provided OneDrive or SharePoint File Request. A File Request is upload-only for participants and does not expose other teams' files.
6. Email the organizers the team ID, submitted filename, and SHA-256. The email is a receipt notice, not the file transport.

Do not commit an entry, attach it to an issue, or open a pull request with it. Organizers should restrict the File Request destination to the small processing group until the embargo ends.

The standard ZIP includes compact metrics, forces, identities, and all profile predictions. If organizers require large native prediction artifacts, place those in private immutable storage and declare `prediction_artifact.private_immutable_url`, `size_bytes`, and `sha256` in `entry.json`. The evaluator records that reference but does not copy the large artifact into the ZIP.

Organizer acknowledgements should state the received filename and SHA-256, without circulating results.
