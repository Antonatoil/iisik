from graphql import GraphQLError


def fail(code: str, message: str) -> None:
    raise GraphQLError(message, extensions={"code": code})


def require_role(actor: dict, *allowed: str) -> None:
    if actor is None:
        fail("UNAUTHENTICATED", "A valid bearer session is required")
    if allowed and actor["role"] not in allowed:
        fail("FORBIDDEN", "This operation is not allowed for this role")
