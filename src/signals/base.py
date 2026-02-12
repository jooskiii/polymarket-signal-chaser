from abc import ABC, abstractmethod


class SignalSource(ABC):
    """Base class for all signal sources.

    Every implementation must provide a ``fetch`` method that returns a list
    of headline dicts with the keys: title, url, published, summary, source.
    """

    @abstractmethod
    def fetch(self):
        """Fetch headlines and return a list of dicts.

        Each dict must contain:
            title     (str): Headline text.
            url       (str): Link to the article.
            published (str): ISO-8601 timestamp.
            summary   (str): Short description / lead text.
            source    (str): Human-readable source name.
        """
        ...
