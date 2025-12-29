def resolve_ttl(config) -> int:
    user_id = config["configurable"]["user_id"]
    thread_id = config["configurable"]["thread_id"]

    VIP_USERS = {1, 42, 99}

    if user_id in VIP_USERS:
        return 60 * 60 * 24 * 7  # 7 days

    return 60 * 60 * 24  # 24 hours
