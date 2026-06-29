''' Shared console logging setup for tradesysx/utils/strategy '''

import logging

# loggers created by this app's own modules (tradesysx.py runs as "__main__")
APP_LOGGER_NAMES = ("__main__", "tradesysx.utils", "tradesysx.strategy")

RESET = "\033[0m"
LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",     # cyan
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[1;31m", # bold red
}


class BracketFormatter(logging.Formatter):
    ''' prefix each message with a colored "[HH:MM:SS LEVEL]" tag '''

    def format(self, record):
        color = LEVEL_COLORS.get(record.levelno, "")
        timestamp = self.formatTime(record, "%H:%M:%S")
        prefix = f"{color}[{timestamp} {record.levelname}]{RESET}"
        return f"{prefix} {record.getMessage()}"


def add_logging_arguments(parser):
    ''' add the shared --loglevel CLI flag to an argparse parser '''
    parser.add_argument(
        '--loglevel',
        type=str.upper,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='set the console logging verbosity (default: INFO)'
    )


def setup_logging(loglevel='INFO'):
    ''' configure console logging based on --loglevel

    Only this app's own loggers (APP_LOGGER_NAMES) follow --loglevel.
    Third-party libraries (yfinance, weasyprint, matplotlib, ...) are
    held at ERROR so their INFO/WARNING chatter doesn't show up.
    '''
    level = getattr(logging, loglevel.upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(BracketFormatter())
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(logging.ERROR)
    root.handlers = [handler]

    for name in APP_LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)

    # some libraries (e.g. weasyprint) set their own logger level on import,
    # overriding root's level - force those back down to ERROR too
    for name, other in logging.root.manager.loggerDict.items():
        if name in APP_LOGGER_NAMES or not isinstance(other, logging.Logger):
            continue
        other.setLevel(logging.ERROR)
