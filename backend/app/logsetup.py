import logging


def configure_logging():
    if logging.getLogger().handlers:
        return  # already configured (e.g. re-imported under --reload)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
