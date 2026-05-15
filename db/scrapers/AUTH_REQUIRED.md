# Vendors that need an authenticated session

Plupdate's public scrapers can't reach these download pages without credentials.
For each one, document below the auth scheme and any plugins your library has
under that vendor — that helps us decide which to invest auth work in.

| Vendor | Auth scheme | Notes |
|---|---|---|
| **Avid** | inMusic / Avid Master Account | Avid hosts AAX core plugins behind the **inMusic Software Center** desktop app. No public per-plugin URLs. Could reverse-engineer the Software Center's API or accept user-supplied URLs. |
| **AIR Music Technology** | inMusic Software Center | Same as Avid — AIR is part of inMusic. Public marketing pages exist but no per-plugin .pkg URLs. |
| **iZotope** | Product Portal login | Each product has its own download page behind login. |
| **Universal Audio** | UA Connect | Native plugins delivered via UA Connect desktop app. No per-plugin URLs. |
| **Waves** | Waves Central | Plugins delivered exclusively through Waves Central desktop app. |
| **Plugin Alliance** | PA Installation Manager | Per-plugin downloads behind login. |
| **Soundtoys** | Account-keyed download page | Each user gets a unique URL after login. Could surface a generic download page. |
| **Goodhertz** | Login required | Single bundle installer (`Goodhertz-Installer-3.13.2-a9ef3f6.pkg`); version visible publicly even though the actual file is gated. |
| **Acustica Audio** | Aquarius desktop app | All deliveries via Aquarius. |
| **Celemony** | myCelemony | Per-product downloads behind login. |
| **Eventide** | Account login | Per-product redirects on `eventideaudio.com/downloads/?product=…`. |
| **McDSP** | Possibly login | Page structure unclear; need to investigate `mcdsp.com/downloads/plugin-downloads/`. |

## Possible strategies (when we want to invest auth work)

1. **User-supplied URL pattern** — when one user submits a real download URL via the Contribute flow, generalize and reuse it for everyone.
2. **Headless-browser scraping** with a per-vendor saved login (Playwright + persistent storage state). Heavier infra; reserve for vendors covering many plugins (Avid/AIR/Waves).
3. **Public marketing pages** — for vendors who post version numbers on product pages but gate downloads, scrape *just* the version + show a vendor page link in the app. Better than nothing.
