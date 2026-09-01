# Backfill execution plane

This one-time Tianjin CCGP history backfill is intentionally isolated from the daily collector.

- Reads the current daily v2 CCGP canonical records/events as its starting baseline.
- Writes only `medicalchannelai:backfill:v1:*` Runtime Cache keys.
- Uses a private Vercel Queue subscriber to split discovery, VERIFIED detail parsing, and correction/termination scans into bounded stages.
- Produces a candidate-only report after the MedicalChannelAI channel-scope filter.
- Does not write the daily collector state and does not write or publish the verified public snapshot.
- Promotion, if any, requires a separate reviewed change after candidate acceptance.

The temporary acceptance start path exists only to run and inspect this bootstrap once. It must be removed after the candidate report is accepted or rejected.
