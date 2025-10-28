# AuDRA-Rad Frontend – Manual Integration Checklist

Use this to confirm the full stack works end-to-end.

## Setup
- Backend running locally at http://localhost:8000 (e.g., `uvicorn src.api.app:app --reload`).
- Guidelines indexed (run the indexing script if needed so recommendations populate).
- Frontend dev server running at http://localhost:3000 (`npm run dev` inside `frontend`).
- Browser cache cleared or hard refresh performed.

## Happy Path
1. Load http://localhost:3000 and confirm the health indicator shows the current API status after a few seconds.
2. In “Load Sample”, pick “Chest CT - Ground-glass nodule”; verify the textarea fills automatically and the character counter turns green.
3. Submit the form and wait for processing to complete.
4. Confirm the Report Viewer displays the original text, status badge, processing time, and session ID (copy button works).
5. Review Findings, Guideline Matches, and Task List sections show populated cards with confidence/urgency styling that matches the backend payload.

## Alternate Sample
1. Submit the “Chest CT - Solid nodule” sample.
2. Confirm the UI replaces prior results and renders updated recommendations/tasks without page reloads.

## Error Handling
1. Stop the backend service and attempt another submission; verify the upload form reports an error and health indicator switches to degraded/unhealthy.
2. Restart the backend and confirm the UI recovers after the next successful submission.

## Session Retrieval (Optional)
- After a successful request, note the session ID and call `/session/{id}` via browser or REST client to ensure the backend responds as expected. The UI should continue functioning without manual refresh.

## Production Build Smoke Test
1. Run `npm run build` and ensure it completes without errors.
2. Optionally serve the contents of `frontend/dist` (e.g., `npm run preview`) and spot-check the main flow.
