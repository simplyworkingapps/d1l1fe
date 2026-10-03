# Facebook, Instagram + LinkedIn post helper

Writes a casual, work-safe post for you 4 times a week (Mon, Wed, Fri, Sun around 9:45am) and pings your phone.
Each post comes in two versions:

- **Facebook:** the post text. One button: **Copy & open Facebook**, then paste.
- **Instagram:** a clean picture with a short line on it, plus a caption with a few hashtags.
  One button: **Share to Instagram** copies the caption and hands the picture to Instagram. Paste the caption when it asks.

Topics rotate between Portland events, Portland life, Chicago, cats, casual style, and gentle wellness.
Event posts are based on real, current listings the app looks up, with a link.

**LinkedIn** is a separate, professional stream on Tuesday and Thursday mornings: recent IT news,
plain-language security, practical tips, what you're learning, the human side of IT, and Portland
tech meetups. One button: **Copy & open LinkedIn**, then paste.

**Cost:** GitHub and the phone notifications are free. The writing uses the Claude API,
which should come to well under a dollar a month at this pace.

---

## Quick setup (about 5 minutes)

**Windows:** double-click **`Setup (Windows).bat`**
**Mac / Linux:** open a terminal in this folder and run `python3 setup.py`

It walks you through everything and does the GitHub work for you: signs you in, creates the
repository, uploads the project, saves your key privately, turns on your post page, connects your
phone, and writes your first posts. You'll just paste your Claude API key and add a channel in the
ntfy phone app.

**You'll need** Python, Git, and the GitHub CLI. If any are missing, setup tells you the exact
one-line command to install them. On Windows, that's:
```
winget install --id Python.Python.3.12 --id Git.Git --id GitHub.cli
```

**Run it again any time** after editing files here, or to swap in a new API key. It updates
everything in place and keeps the posts already made.

---

## Manual setup (if you'd rather click through it yourself)

### 1. Put the project on GitHub
1. Create a free account at github.com if you don't have one.
2. Make a **new public repository**, e.g. `posts`. (Public is required for the free page.
   The page is hidden from search engines, and everything on it is meant to go on Facebook anyway.)
3. Upload everything in this folder to it, or from a terminal:
   ```
   git remote add origin https://github.com/YOUR-NAME/posts.git
   git push -u origin main
   ```

### 2. Get a Claude API key
1. Go to console.anthropic.com, sign up, and add a few dollars of credit.
2. Create an API key and copy it.
3. In your repository: **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `ANTHROPIC_API_KEY`, value: the key.

### 3. Set up phone notifications
1. Install the free **ntfy** app (Android or iPhone).
2. Make up a long, random name nobody would guess, like `my-posts-k7q2x9mw4`. Anyone who knows it can see your pings.
3. In ntfy, tap **+** and subscribe to that name.
4. Add another repository secret. Name: `NTFY_TOPIC`, value: the name you made up.

### 4. Turn on your post page
**Settings → Pages → Build and deployment**: Source **Deploy from a branch**, branch **main**, folder **/docs**. Save.
Your page will be at `https://YOUR-NAME.github.io/posts/`. Bookmark it on your phone.

### 5. Check your IT background (important for LinkedIn)
Your experience and certifications are already filled in under `background:` in the `linkedin:`
section of `poster/config.yaml`. LinkedIn posts will **only** mention what's written there, so
they never claim something you haven't done. Update it whenever your experience grows. If you'd like posts to occasionally say you're open to new roles,
set `mention_job_search: true`.

### 6. Try it
**Actions → Write a post → Run workflow.** About two minutes later your phone buzzes.
The first time, GitHub may ask you to enable Actions for the repo; click the green button.

---

## Day to day
- Phone buzzes → tap it → the page opens on the right tab (Facebook, Instagram, or LinkedIn).
- **Facebook:** **Copy & open Facebook** → start a new post → paste → Post.
- **Instagram:** **Share to Instagram** → choose Instagram → pick Feed → paste the caption → Share.
  (On a computer, it saves the picture and copies the caption instead.)
- **LinkedIn:** give it a quick read, then **Copy & open LinkedIn** → paste → Post.
- Tap **Mark posted** so the page moves on to the next one. Each platform is tracked separately, on that phone.
- Tap any earlier post in the list to bring it back up.
- Don't like one? Skip it. Want one now? **Actions → Write a post** (or **Write a LinkedIn post**) **→ Run workflow** (works from the GitHub phone app), optionally picking a topic.

## Changing things
- **Voice, topics, how often each topic comes up:** edit `poster/config.yaml` right on GitHub.
- **Picture colors and labels:** the top of `poster/card.py`.
- **LinkedIn voice, background, and topics:** the `linkedin:` section of `poster/config.yaml`.
- **Posting days and time:** the `cron` line in `.github/workflows/post.yml` (LinkedIn: `linkedin.yml`).
- If GitHub ever emails that it paused the schedule, open **Actions** and click **Enable workflow**.

## Safety net
Every post is written under strict work-safe rules (no politics, drinking, swearing, dating,
job complaints, medical advice, or made-up claims about you), then given a second read-through just for tone:
anything that could come off as cocky, smug, or cold gets softened, and it adds a little
empathy where it fits naturally. Finally it's checked against a blocked-word list before it's saved. LinkedIn posts get extra rules: no invented experience, no criticizing companies or people,
no hype or engagement bait, and a tone check written with hiring managers in mind.
Nothing is ever posted anywhere without you sharing it yourself.
