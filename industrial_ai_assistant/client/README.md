# Industrial AI Assistant - Frontend

This is the React frontend for the Industrial AI Assistant.

## Setup

1.  **Install Dependencies:**
    ```bash
    cd client
    npm install
    ```

2.  **Development Mode (Hot Reload):**
    ```bash
    npm run dev
    ```
    This will start the frontend server (usually at `http://localhost:5173`). It is configured to proxy API requests to `http://localhost:8001`.

3.  **Production Build:**
    To serve the frontend via the Python backend, you must build it first:
    ```bash
    npm run build
    ```
    This creates a `dist` directory. The FastAPI backend is configured to serve static files from this directory.

## Structure
- `src/components`: Reusable UI components.
- `src/pages`: Top-level page views.
- `src/api`: API integration.