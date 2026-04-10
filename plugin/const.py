"""Constants for Douyin parser plugin."""

DOMAIN = "douyin"

# Platform info
PLATFORM_CODE = "douyin"
PLATFORM_NAME = "抖音"
PLATFORM_URL = "https://www.douyin.com"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/抖音.png"

# URL pattern — matches canonical video/note/gallery/slides pages and v.douyin.com short links.
# Uses re.match() so the host must appear at the start of the string.
URL_PATTERN = (
    r"https?://(?:"
    r"(?:www\.)?douyin\.com/(?:video|note|gallery|slides)/\d+"
    r"|v\.douyin\.com/\S+"
    r")"
)

BASE_URL = "https://www.douyin.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# Aweme type codes that indicate gallery (image/note) content rather than video.
GALLERY_AWEME_TYPES = {2, 68, 150}
