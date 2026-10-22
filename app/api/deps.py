from fastapi import Request


def repository(request: Request):
    return request.app.state.repository
