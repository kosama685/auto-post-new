# Blogger OAuth setup

Blogger publishing requires Google OAuth for the Google account that owns or manages the target blog.

## 1. Create a Google Cloud project

1. Open Google Cloud Console.
2. Create a project.
3. Enable **Blogger API v3**.
4. Configure OAuth consent screen.
5. Create OAuth client credentials.

For local use, choose **Desktop app** or **Web application** with a localhost redirect.

## 2. Download credentials

Download the OAuth JSON file and place it in the project root, for example:

```text
client_secret.json
```

Set this in `.env`:

```bash
GOOGLE_CLIENT_SECRET_FILE="client_secret.json"
GOOGLE_TOKEN_FILE="token.json"
BLOGGER_BLOG_ID="your-blog-id"
```

## 3. Find your Blogger blog ID

Open Blogger admin. The blog ID is visible in URLs like:

```text
https://www.blogger.com/blog/posts/1234567890123456789
```

The long number is `BLOGGER_BLOG_ID`.

## 4. Authorize once

```bash
python main.py authorize-blogger
```

A browser window opens. Sign in with the account that owns the blog and approve access.

The token is saved to `token.json`. Keep it private.

## 5. Publish as draft first

Keep this default for safer health content review:

```bash
BLOGGER_POST_AS_DRAFT="true"
```
