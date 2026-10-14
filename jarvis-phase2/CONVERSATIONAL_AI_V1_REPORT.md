# Conversational AI V1

Root cause: `/api/chat` sent almost every message to the legacy ShadowRunner;
ContextCompiler defaulted to `decision_summary`, and chat rendered a record
count. No authorised general conversational provider is registered.

The additive router separates simple, company, analysis, research, action and
general reasoning requests. Company questions use the minimum allowlisted
source. Analysis is planned without execution. Research fails honestly.
Actions stay `PROPOSED` with zero execution. General reasoning reports
`AI_PROVIDER_UNAVAILABLE`.

Static UI is unchanged because the Execution UI workstream owns it. Browser
speech recognition is `WAITING_UI_MERGE`; transcription will use the same chat
endpoint and authorization boundary.
