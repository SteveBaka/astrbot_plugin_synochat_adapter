from astrbot.api import star


class Main(star.Star):
    def __init__(self, context: star.Context):
        self.context = context
        from .synology_chat_adapter import SynologyChatAdapter  # noqa: F401
