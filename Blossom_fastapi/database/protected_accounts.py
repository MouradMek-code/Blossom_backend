"""Accounts no automatic rule may delete: the one given to Google Play's
reviewers (Play Console > App content > App access), who may be anywhere,
India included, and may have no photos.

On the server: PROTECTED_ACCOUNTS=review@example.com,another_username
(emails or usernames, separated by commas). Not a privilege: an admin can
still delete these accounts by hand.
"""
import os


def is_protected(user) -> bool:
    names = {name.strip().lower() for name in os.getenv("PROTECTED_ACCOUNTS", "").split(",") if name.strip()}
    return (user.email or "").lower() in names or (user.username or "").lower() in names
