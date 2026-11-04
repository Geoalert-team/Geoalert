from utils.permissions import BFP_ROLE, is_bfp

# Who can change any post, not only their own
MODERATORS = ('DRRMO_Officer', 'System_Admin')


def source_for(user):
    """The office a new post is from: BFP for BFP personnel; DRRMO for DRRMO and admins."""
    return 'BFP' if is_bfp(user) else 'DRRMO'


def can_manage(user, post):
    """Whether this person may edit or delete the post: its BFP author, or any DRRMO officer or admin."""
    if not getattr(user, 'is_authenticated', False) or user.role is None:
        return False
    role = user.role.name
    return role in MODERATORS or (role == BFP_ROLE and post.created_by_id == user.id)
