# SPDX-License-Identifier: GPL-3.0-or-later
"""Update check against the project's GitHub Releases.

The Releases page is the whole distribution channel: no server, no account, no token.
Nothing here draws a window or talks to DaVinci Resolve, so the same code serves the
script window and the terminal. Being offline is not an error: check() reports and
never raises. The program only starts the download of the latest installer: it never
installs anything.

Notes on the design (keep in mind before "simplifying"):

* The check asks the redirect of /releases/latest instead of the JSON API: GitHub
  answers 302 with the tag in the Location header, it costs a few hundred bytes and
  carries no x-ratelimit headers, so the common "I am up to date" case spends nothing
  of the 60 unauthenticated requests per hour. The API is asked only when there really
  is something newer.
* urlopen's timeout does NOT bound DNS resolution: on an unreachable name it can block
  ~30 seconds. Callers must keep these functions off the thread that paints the window.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from . import __version__

REPO = 'ivan-94m/SLogMetaRaw'
LATEST_REDIRECT = 'https://github.com/%s/releases/latest' % REPO
API_LATEST = 'https://api.github.com/repos/%s/releases/latest' % REPO
RELEASES_PAGE = 'https://github.com/%s/releases' % REPO
TAG_PAGE = 'https://github.com/%s/releases/tag/%%s' % REPO

SUPPORT_DIR = os.path.expanduser('~/Library/Application Support/SLogMetaRaw')
STATE_PATH = os.path.join(SUPPORT_DIR, 'update.json')
CACHE_TTL = 60  # seconds: a fresh answer is reused instead of asking GitHub again

SEMVER_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
TAG_IN_URL_RE = re.compile(r'/releases/tag/([^/?#]+)')

# GitHub answers 403 to a request without a User-Agent.
_AGENT = 'SLogMetaRaw/%s (macOS)' % __version__
_HEADERS = {'User-Agent': _AGENT}
_API_HEADERS = dict(_HEADERS, **{'Accept': 'application/vnd.github+json'})


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3). None when it is not a version at all."""
    match = SEMVER_RE.match(str(text or '').strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(current, latest):
    """True only when both parse and latest really is ahead."""
    cur, new = parse_version(current), parse_version(latest)
    return bool(cur and new and new > cur)


def blank(current=None):
    """The shape check() returns, with nothing in it. One place defines the keys."""
    return {'ok': False, 'current': current or __version__, 'latest': '', 'newer': False,
            'tag': '', 'notes': '', 'title': '', 'page': RELEASES_PAGE,
            'dmg_url': '', 'dmg_name': '', 'size': 0, 'checked_at': 0.0, 'error': ''}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand the 302 back instead of following it: the tag is in the Location header."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def latest_tag(timeout=6.0):
    """The tag of the newest published release, from the /releases/latest redirect.

    GitHub leaves drafts and pre-releases out of "latest", so neither can ever be
    offered to anyone. Returns '' when the repository has no release yet.
    """
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(LATEST_REDIRECT, method='HEAD', headers=_HEADERS)
    location = ''
    try:
        response = opener.open(request, timeout=timeout)
        location = response.headers.get('Location') or ''
        response.close()
    except urllib.error.HTTPError as err:
        try:
            if err.code in (301, 302, 303, 307, 308):
                location = err.headers.get('Location') or ''
            elif err.code == 404:
                return ''                  # no releases published yet
            else:
                raise
        finally:
            err.close()                    # HTTPError is a response too: do not leak it
    match = TAG_IN_URL_RE.search(location)
    if not match:
        raise ValueError('risposta di GitHub inattesa (nessun tag in %r)' % location)
    return match.group(1)


def release_details(timeout=6.0):
    """Notes and installer for the newest release. Only called when there IS an update."""
    request = urllib.request.Request(API_LATEST, headers=_API_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        release = json.load(response)
    # picked by extension, not by name: the installer may be called something else
    # one day, and an update that broke over a rename would be a poor trade
    dmg = next((a for a in release.get('assets') or []
                if (a.get('name') or '').lower().endswith('.dmg')), None) or {}
    return {
        'notes': release.get('body') or '',
        'title': release.get('name') or '',
        'page': release.get('html_url') or RELEASES_PAGE,
        'dmg_url': dmg.get('browser_download_url') or '',
        'dmg_name': dmg.get('name') or '',
        'size': int(dmg.get('size') or 0),
    }


def describe_error(exc):
    """One sentence in Italian, for the status bar. Never a traceback."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 403:
            return 'GitHub ha rifiutato la richiesta: riprova tra un po\''
        if exc.code == 404:
            return 'Nessuna versione pubblicata su GitHub'
        return 'GitHub ha risposto %s' % exc.code
    if isinstance(exc, urllib.error.URLError):
        return 'Nessuna connessione a GitHub'
    if isinstance(exc, ValueError):
        return 'Risposta di GitHub non comprensibile'
    return 'Controllo non riuscito'


def read_state():
    try:
        with open(STATE_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(result):
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        with open(STATE_PATH, 'w', encoding='utf-8') as fh:
            json.dump(result, fh, ensure_ascii=False)
    except OSError:
        pass


def check(current=None, timeout=6.0):
    """Ask GitHub what the newest release is. Never raises; reports in 'error'.

    Slow by nature (see the module docstring on DNS): call it from a worker thread.
    """
    result = blank(current)
    cached = read_state()
    if (cached.get('checked_at') or 0) > time.time() - CACHE_TTL and cached.get('ok'):
        cached['checked_at'] = time.time()
        return cached
    try:
        tag = latest_tag(timeout=timeout)
        if not tag:
            result['ok'] = True
        else:
            result['tag'] = tag
            result['latest'] = tag.lstrip('vV')
            result['page'] = TAG_PAGE % tag
            result['newer'] = is_newer(result['current'], result['latest'])
            if result['newer']:
                result.update(release_details(timeout=timeout))
                if not result['dmg_url']:
                    # a release without an installer: still tell the truth
                    result['error'] = 'La release %s non allega un installer' % result['latest']
            else:
                result['ok'] = True
    except Exception as exc:
        result['error'] = describe_error(exc)
    result['checked_at'] = time.time()
    write_state(result)
    return result
