# Cyberbullying and spam detection

This Flask app classifies messages as normal, spam, or cyberbullying.

## Deploy on Render

1. Push this repository to GitHub.
2. In the [Render dashboard](https://dashboard.render.com/), select **New → Blueprint** and connect the repository.
3. Render reads `render.yaml` to install dependencies and start the web service. On success, Render provides its public `onrender.com` URL.

The blueprint generates a Flask session secret automatically. The free service stores its SQLite database under `/tmp`, so saved prediction history is temporary and may be lost when the service restarts or redeploys.

For local development, install `requirements.txt` and run `python app.py`.
