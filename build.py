#!/usr/bin/env python3
"""Build static site from partials + page fragments.

Reads:
- pages.json      — page registry + site metadata
- blog.json       — blog posts (expanded into /article/{slug}.html)
- _partials/head.html   — shared <head> template
- _partials/nav.html    — shared navigation
- _partials/footer.html — shared footer + closing scripts
- pages/{fragment}.html — main-content fragment per page

Writes dist/ — deploy-ready static site.
"""
import datetime as _dt
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
PARTIALS = ROOT / "_partials"
PAGES = ROOT / "pages"

SITE_URL = "https://www.cleanlivingpoolandspa.com"

# Head content injected for each blog post (BlogPosting schema + per-post styles)
BLOG_POST_HEAD_TEMPLATE = """<meta name="twitter:title" content="{{META_TITLE}}">
<meta name="twitter:description" content="{{DESCRIPTION}}">
<meta name="twitter:image" content="{{SITE_URL}}{{FEATURED_IMAGE}}">

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "{{TITLE}}",
  "datePublished": "{{DATE}}",
  "author": {
    "@type": "Person",
    "name": "{{AUTHOR}}"
  },
  "description": "{{EXCERPT}}",
  "image": "{{SITE_URL}}{{FEATURED_IMAGE}}",
  "mainEntityOfPage": "{{SITE_URL}}/article/{{SLUG}}",
  "publisher": {
    "@type": "LocalBusiness",
    "name": "Clean Living Pool and Spa",
    "telephone": "+17025393927",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "6845 W Cheyenne Ave, Suite F",
      "addressLocality": "Las Vegas",
      "addressRegion": "NV",
      "postalCode": "89130",
      "addressCountry": "US"
    }
  }
}
</script>

<style>
  .post-hero { padding: clamp(220px, 24vh, 260px) 24px clamp(36px, 5vh, 56px); background: #fff; color: #0d1b2a; }
  .post-hero .container { max-width: 1200px; margin: 0 auto; }
  .post-hero .crumbs { font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: #6b7a8f; margin-bottom: 20px; }
  .post-hero .crumbs a { color: inherit; text-decoration: none; border-bottom: 1px solid rgba(13,27,42,.2); }
  .post-hero .crumbs a:hover { border-bottom-color: #0e7ac6; color: #0e7ac6; }
  .post-hero .cat { display: inline-block; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; background: rgba(14,122,198,.1); color: #0e7ac6; padding: 4px 10px; border-radius: 4px; margin-bottom: 16px; }
  .post-hero h1 { font-size: clamp(28px, 5vw, 52px); line-height: 1.15; margin: 0; color: #0d1b2a; }
  .post-hero .post-meta { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 20px; font-size: 14px; color: #6b7a8f; }
  .post-hero .post-meta .sep { opacity: .5; }
  .post-feature { background: #f7f7f7; padding: 32px 24px; }
  .post-feature .container { max-width: 1000px; margin: 0 auto; }
  .post-feature img { display: block; width: 100%; max-height: 520px; object-fit: cover; border-radius: 8px; }
  .post-body { padding: clamp(40px, 6vh, 72px) 24px; }
  .post-body .container { max-width: 780px; margin: 0 auto; font-size: 17px; line-height: 1.7; color: #222; }
  .post-body h2 { font-size: 26px; margin: 40px 0 16px; color: #0e7ac6; }
  .post-body h3 { font-size: 20px; margin: 28px 0 12px; color: #0e7ac6; }
  .post-body p { margin: 0 0 16px; }
  .post-body ul, .post-body ol { margin: 0 0 16px; padding-left: 24px; }
  .post-body ul li, .post-body ol li { margin-bottom: 8px; }
  .post-body a { color: #0e7ac6; }
  .post-body img { max-width: 100%; height: auto; display: block; margin: 24px 0; border-radius: 8px; }
  .post-body blockquote { margin: 24px 0; padding: 18px 24px; border-left: 4px solid #0e7ac6; background: #f7f7f7; font-style: italic; color: #444; }
  .post-cta { background: #0e7ac6; color: #fff; padding: clamp(40px, 6vh, 64px) 24px; }
  .post-cta .container { max-width: 1200px; margin: 0 auto; }
  .post-cta .cta-inner { display: flex; justify-content: space-between; align-items: center; gap: 28px; flex-wrap: wrap; }
  .post-cta .eyebrow { font-size: 12px; letter-spacing: .12em; text-transform: uppercase; opacity: .85; }
  .post-cta h2 { font-size: clamp(24px, 3vw, 34px); line-height: 1.1; margin: 10px 0 0; }
  .post-cta p { opacity: .9; margin-top: 12px; max-width: 44ch; }
  .post-cta .actions { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .post-cta .btn-primary { display: inline-block; background: #fff; color: #0e7ac6; padding: 14px 22px; font-weight: 600; border-radius: 6px; text-decoration: none; font-size: 16px; }
  .post-cta .btn-primary:hover { background: #f0f0f0; }
  .post-cta .back-link { color: rgba(255,255,255,.8); text-decoration: none; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,.4); padding-bottom: 2px; }
  .post-cta .back-link:hover { color: #fff; }
</style>"""


def load_json(name):
    p = ROOT / name
    return json.loads(p.read_text()) if p.exists() else None


def render(template, **subs):
    def repl(m):
        return str(subs.get(m.group(1), ""))
    return re.sub(r"\{\{([A-Z_]+)\}\}", repl, template)


def apply_vars(html, variables):
    for k, v in variables.items():
        html = html.replace("{{" + k + "}}", v)
    return html


def balance_divs(fragment_html):
    """Pad the fragment with extra opening <div>s if it has more </div> than <div>.

    Some page fragments (e.g. contact-us, services pages) carry unbalanced
    </div> closes that would pop out of the content-wrapper and leave the
    footer as a body-level sibling. That drops the overflow:clip that
    content-wrapper applies to the footer's 1500px background waves, so
    non-home pages end up with ~500px of empty space below the footer.
    Balance the fragment defensively so the footer is always nested inside
    content-wrapper.
    """
    opens = len(re.findall(r"<div[\s>]", fragment_html))
    closes = fragment_html.count("</div>")
    if closes > opens:
        return "<div>" * (closes - opens) + fragment_html
    return fragment_html


def assemble(page, head_tpl, nav_html, footer_html, fragment_html, site_defaults=None):
    canonical = page.get("canonical", "")
    default_og_image = f"{SITE_URL}/assets/images/clps-logo.webp"
    robots = page.get("robots", "")
    robots_tag = f'<meta name="robots" content="{robots}">' if robots else ""
    head = render(
        head_tpl,
        TITLE=page.get("meta_title") or page["title"],
        DESCRIPTION=page["description"],
        PAGE_STYLES=page.get("pageStyles", ""),
        PAGE_ROBOTS=robots_tag,
        CANONICAL=canonical,
        OG_URL=page.get("ogUrl", canonical),
        OG_TITLE=page.get("ogTitle") or page.get("meta_title") or page["title"],
        OG_DESCRIPTION=page.get("ogDescription") or page["description"],
        OG_TYPE=page.get("ogType", "website"),
        OG_IMAGE=page.get("ogImage", default_og_image),
    )
    variables = dict(site_defaults or {})
    variables.update(page.get("vars", {}))
    nav = apply_vars(nav_html, variables)
    frag = apply_vars(balance_divs(fragment_html), variables)
    foot = apply_vars(footer_html, variables)
    return head + nav + "\n" + frag + "\n" + foot


def format_date(iso_date):
    if not iso_date:
        return ""
    try:
        return _dt.date.fromisoformat(iso_date).strftime("%B %d, %Y")
    except Exception:
        return iso_date


def main():
    cfg = load_json("pages.json")
    if not cfg:
        print("ERROR: pages.json not found")
        return

    blog = load_json("blog.json") or {}
    site = cfg["site"]
    global SITE_URL
    SITE_URL = site["url"].rstrip("/")

    head_tpl = (PARTIALS / "head.html").read_text()
    nav_html = (PARTIALS / "nav.html").read_text()
    footer_html = (PARTIALS / "footer.html").read_text()
    site_defaults = site.get("defaults", {})

    # Reset dist/
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    # Copy static asset directories
    for static_dir in ("assets", "uploads", "css", "js", "fonts", "images"):
        if (ROOT / static_dir).exists():
            shutil.copytree(ROOT / static_dir, DIST / static_dir)

    # Copy CF Pages special files
    for special in ("_redirects", "_headers"):
        if (ROOT / special).exists():
            shutil.copy2(ROOT / special, DIST / special)

    # Copy loose root-level static files
    _skip_root_files = {"build.py", "pages.json", "blog.json", ".gitignore", ".DS_Store",
                        "sitemap.xml", "robots.txt", "_redirects", "_headers", "README.md"}
    for item in ROOT.iterdir():
        if not item.is_file():
            continue
        if item.name in _skip_root_files:
            continue
        if item.suffix == ".html":
            continue  # handled by page fragments
        shutil.copy2(item, DIST / item.name)

    written = []

    def canonical_for(slug):
        if slug == "index":
            return f"{SITE_URL}/"
        if slug == "404":
            return f"{SITE_URL}/"
        # /services/pool-cleaning becomes canonical - use slashes appropriately
        if slug.startswith("services-"):
            # services-pool-cleaning -> /services/pool-cleaning
            svc = slug.replace("services-", "services/")
            return f"{SITE_URL}/{svc}"
        return f"{SITE_URL}/{slug}"

    # Build content pages
    for page in cfg["pages"]:
        frag_path = PAGES / page["fragment"]
        if not frag_path.exists():
            print(f"  SKIP {page['slug']}: missing fragment {frag_path.name}")
            continue

        page["canonical"] = canonical_for(page["slug"])
        fragment = frag_path.read_text()
        html = assemble(page, head_tpl, nav_html, footer_html, fragment, site_defaults)

        slug = page["slug"]
        if slug == "index":
            out = DIST / "index.html"
        elif slug == "404":
            out = DIST / "404.html"
        elif slug.startswith("services-"):
            svc = slug.replace("services-", "services/")
            out = DIST / f"{svc}.html"
        else:
            out = DIST / f"{slug}.html"

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        written.append((slug, out.stat().st_size))

    # Build blog posts under /article/{slug}.html
    posts = blog.get("posts", [])
    blog_post_frag = PAGES / cfg.get("blog", {}).get("postFragment", "blog-post.html")

    if posts and blog_post_frag.exists():
        article_dir = DIST / "article"
        article_dir.mkdir(parents=True, exist_ok=True)
        post_tpl = blog_post_frag.read_text()

        for p in posts:
            body = p.get("body", "")
            if not body:
                print(f"  SKIP article/{p['slug']}: no body content")
                continue

            raw_date = p.get("date", "")
            date_fmt = format_date(raw_date)
            raw_cat = p.get("category", "")
            cat_display = raw_cat.replace("-", " ").title() if raw_cat else ""
            cat_html = f'<span class="cat">{cat_display}</span>' if cat_display else ''
            featured = p.get("featured_image", "")
            alt = p.get("alt_text", p.get("title", ""))

            frag = post_tpl
            for k, v in [
                ("TITLE", p["title"]),
                ("SLUG", p["slug"]),
                ("DATE", raw_date),
                ("DATE_FORMATTED", date_fmt),
                ("AUTHOR", p.get("author", "Clean Living Pool and Spa")),
                ("BODY", body),
                ("FEATURED_IMAGE", featured),
                ("ALT_TEXT", alt),
                ("CATEGORY", cat_display),
                ("CATEGORY_HTML", cat_html),
                ("EXCERPT", p.get("excerpt", "")),
            ]:
                frag = frag.replace("{{" + k + "}}", v)

            # Head extras: BlogPosting schema + post styles
            meta_title = p.get("meta_title") or p["title"]
            description = p.get("description") or p.get("excerpt", "")
            head_extras = BLOG_POST_HEAD_TEMPLATE
            for k, v in [
                ("SITE_URL", SITE_URL),
                ("TITLE", p["title"].replace('"', '&quot;')),
                ("META_TITLE", meta_title.replace('"', '&quot;')),
                ("DESCRIPTION", description.replace('"', '&quot;')),
                ("SLUG", p["slug"]),
                ("DATE", raw_date),
                ("AUTHOR", p.get("author", "Clean Living Pool and Spa")),
                ("FEATURED_IMAGE", featured),
                ("EXCERPT", p.get("excerpt", "").replace('"', '&quot;')),
            ]:
                head_extras = head_extras.replace("{{" + k + "}}", v)

            og_image = f"{SITE_URL}{featured}" if featured.startswith("/") else featured

            post_page = {
                "slug": f"article/{p['slug']}",
                "title": p["title"],
                "meta_title": meta_title,
                "description": description,
                "canonical": f"{SITE_URL}/article/{p['slug']}",
                "ogUrl": f"{SITE_URL}/article/{p['slug']}",
                "ogType": "article",
                "ogImage": og_image,
                "ogTitle": meta_title,
                "ogDescription": description,
                "pageStyles": head_extras,
            }
            html = assemble(post_page, head_tpl, nav_html, footer_html, frag, site_defaults)
            out = article_dir / f"{p['slug']}.html"
            out.write_text(html)
            written.append((post_page["slug"], out.stat().st_size))

    # Copy blog/posts.json into dist/blog/ so the listing page can fetch it
    blog_src = ROOT / "blog"
    if blog_src.exists():
        (DIST / "blog").mkdir(exist_ok=True)
        posts_json = blog_src / "posts.json"
        if posts_json.exists():
            shutil.copy2(posts_json, DIST / "blog" / "posts.json")

    # sitemap.xml + robots.txt
    today = _dt.date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for slug, _ in written:
        page = next((p for p in cfg["pages"] if p["slug"] == slug), None)
        if page and page.get("noindex"):
            continue
        # Convert slug back to URL path
        if slug == "index":
            path = ""
        elif slug.startswith("services-"):
            path = slug.replace("services-", "services/")
        else:
            path = slug
        priority = "1.0" if slug == "index" else "0.8"
        lines += [
            "  <url>",
            f"    <loc>{SITE_URL}/{path}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    lines.append("</urlset>\n")
    (DIST / "sitemap.xml").write_text("\n".join(lines))
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n"
    )

    print(f"Wrote {len(written)} pages to {DIST}:")
    for slug, size in written[:20]:
        print(f"  {slug:60s} {size:>9,} bytes")
    if len(written) > 20:
        print(f"  ... plus {len(written) - 20} more")
    print("  + sitemap.xml, robots.txt")


if __name__ == "__main__":
    main()
