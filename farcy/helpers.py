"""Helper methods and classes."""

from collections import defaultdict
from github3 import GitHub
from github3.exceptions import GitHubError
import os
import sys
from .const import FARCY_COMMENT_START, NUMBER_RE, CONFIG_DIR
from .exceptions import FarcyException

IS_FARCY_COMMENT = FARCY_COMMENT_START.split('v')[0]


def added_lines(patch):
    """Return a mapping of added line numbers to the patch line numbers."""
    added = {}
    lineno = None
    position = 0
    for line in patch.split('\n'):
        if line.startswith('@@'):
            lineno = int(NUMBER_RE.match(line.split('+')[1]).group(1))
        elif line.startswith(' '):
            lineno += 1
        elif line.startswith('+'):
            added[lineno] = position
            lineno += 1
        elif line == "\ No newline at end of file":
            continue
        else:
            assert line.startswith('-')
        position += 1
    return added


def ensure_config_dir():
    """Ensure Farcy config dir exists."""
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, mode=0o700)


def extract_issues(text):
    """Extract farcy violations from a text."""
    if not is_farcy_comment(text):
        return []
    # Strip out start of bullet point, ignore first line
    return [line[2:] for line in text.split('\n')[1:]]


def filter_comments_from_farcy(comments):
    """Filter comments for farcy comments."""
    return (comment for comment in comments if is_farcy_comment(comment.body))


def filter_comments_by_path(comments, path):
    """Filter a comments iterable by a file path."""
    return (comment for comment in comments if comment.path == path)


def get_session():
    """Fetch and/or load API authorization token for GITHUB."""
    ensure_config_dir()
    credential_file = os.path.join(CONFIG_DIR, 'github_auth')
    if os.path.isfile(credential_file):
        with open(credential_file) as fd:
            token = fd.readline().strip()
        gh = GitHub(token=token)
        try:  # Test connection before starting
            gh.is_starred('github', 'gitignore')
            return gh
        except GitHubError as exc:
            raise_unexpected(exc.code)
            sys.stderr.write('Invalid saved credential file.\n')

    from getpass import getpass
    from github3 import authorize

    user = prompt('GITHUB Username')
    try:
        auth = authorize(
            user, getpass('Password for {0}: '.format(user)), 'repo',
            'Farcy Code Reviewer',
            two_factor_callback=lambda: prompt('Two factor token'))
    except GitHubError as exc:
        raise_unexpected(exc.code)
        raise FarcyException(exc.message)

    with open(credential_file, 'w') as fd:
        fd.write('{0}\n{1}\n'.format(auth.token, auth.id))
    return GitHub(token=auth.token)


def is_farcy_comment(text):
    """Return boolean if text was generated by Farcy."""
    return text.startswith(IS_FARCY_COMMENT)


def issues_by_line(comments, path):
    """Return dictionary mapping patch line nr to list of issues for a path."""
    by_line = defaultdict(list)
    for comment in filter_comments_by_path(comments, path):
        issues = extract_issues(comment.body)
        if issues:
            by_line[comment.position].extend(issues)
    return by_line


def parse_bool(value):
    """Return whether or not value represents a True or False value."""
    if isinstance(value, basestring):
        return value.lower() in ['1', 'on', 't', 'true', 'y', 'yes']
    return bool(value)


def parse_set(item_or_items, normalize=False):
    """Return a set of unique tokens in item_or_items.

    :param item_or_items: Can either be a string, or an iterable of strings.
      Each string can contain one or more items separated by commas, these
      items will be expanded, and empty tokens will be removed.
    :param normalize: When true, lowercase all tokens.

    """
    if isinstance(item_or_items, basestring):
        item_or_items = [item_or_items]

    items = set()
    for item in item_or_items:
        for token in (x.strip() for x in item.split(',') if x.strip()):
            items.add(token.lower() if normalize else token)
    return items if items else None


def plural(items, word):
    """Return number of items followed by the right form  of ``word``.

    ``items`` can either be an int or an object whose cardinality can be
    discovered via `len(items)`.

    The plural of ``word`` is assumed to be made by adding an ``s``.

    """
    item_count = items if isinstance(items, int) else len(items)
    word = word if item_count == 1 else word + 's'
    return '{0} {1}'.format(item_count, word)


def prompt(msg):
    """Output message and return striped input."""
    sys.stdout.write('{0}: '.format(msg))
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def raise_unexpected(code):
    """Called from with in an except block.

    Re-raises the exception if we don't know how to handle it.

    """
    if code != 401:
        raise


def split_dict(data, keys):
    """Split a dict in a dict with keys `keys` and one with the rest."""
    with_keys = {}
    without_keys = {}
    for key, value in data.items():
        if key in keys:
            with_keys[key] = value
        else:
            without_keys[key] = value
    return with_keys, without_keys


def subtract_issues_by_line(by_line, by_line2):
    """Return a dict with all issues in by_line that are not in by_line2."""
    result = {}
    for key, values in by_line.items():
        exclude = by_line2.get(key, [])
        filtered = [value for value in values if value not in exclude]
        if filtered:
            result[key] = filtered
    return result
