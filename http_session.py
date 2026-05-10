import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session() -> requests.Session:
    retry = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"POST"},
        backoff_factor=0.6,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
