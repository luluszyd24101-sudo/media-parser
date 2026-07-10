# ======= 环境配置开始 =======
from pathlib import Path
import sys
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.append(root_dir)
# ===========================

import json
import re
import urllib3
import warnings
import copy
import requests
from utils.web_fetcher import UrlParser
from utils.douyin_utils.bogus_sign_utils import CommonUtils
from configs.logging_config import get_logger
logger = get_logger(__name__)
from src.parsers.base_parser import BaseParser

warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)


class DouyinParser(BaseParser):
    """抖音解析器 —— 官方API + 第三方API 双重兜底"""

    # 第三方解析 API（短链项目使用的公开服务）
    FALLBACK_API = "https://api.bugpk.com/api/douyin.php"

    def __init__(self, real_url):
        super().__init__(real_url)
        self.common_utils = CommonUtils()
        self.headers = {
            'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            'Accept': 'application/json, text/plain, */*',
            'sec-ch-ua-mobile': '?0',
            'User-Agent': self.common_utils.user_agent,
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self.ms_token = self.common_utils.get_ms_token()
        self.ttwid = None
        self.webid = None
        self.aweme_id = UrlParser.get_video_id(self.real_url)
        self.data = self._fetch_video_data()

    # ---------- 核心：尝试所有方案获取数据 ----------

    def _fetch_video_data(self):
        """按优先级尝试所有解析方案"""
        for attempt_name in ['official_api', 'fallback_api']:
            try:
                if attempt_name == 'official_api':
                    result = self._try_official_api()
                else:
                    result = self._try_fallback_api()

                if result and self._is_valid_result(result):
                    logger.info(f"Douyin: {attempt_name} 解析成功")
                    return result

            except Exception as e:
                logger.warning(f"Douyin: {attempt_name} 解析异常: {e}")
                continue

        logger.error("Douyin: 所有解析方案均失败")
        return {}

    def _is_valid_result(self, data):
        """检查返回的数据是否包含有效视频信息"""
        if not data:
            return False
        detail = data.get('aweme_detail') or {}
        if not detail:
            return False
        video = detail.get('video') or {}
        return bool(video.get('play_addr') or video.get('bit_rate'))

    # ---------- 方案一：官方 API ----------

    def _try_official_api(self):
        self.ttwid = self._get_or_refresh_ttwid()
        self.webid = self._get_webid()

        if not self.aweme_id:
            logger.error("Douyin: 无法获取视频ID")
            return None

        referer_url = f"https://www.douyin.com/video/{self.aweme_id}?previous_page=web_code_link"
        play_url = (
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
            f"?device_platform=webapp&aid=6383&channel=channel_pc_web"
            f"&aweme_id={self.aweme_id}&msToken={self.ms_token}"
        )

        new_headers = copy.deepcopy(self.headers)
        new_headers['Referer'] = referer_url
        new_headers['Cookie'] = f"ttwid={self.ttwid}"

        abogus = self.common_utils.get_abogus(play_url, self.common_utils.user_agent)
        url = f"{play_url}&a_bogus={abogus}"

        try:
            response = self.session.get(url, headers=new_headers, verify=False, timeout=10)
            if response.status_code == 200 and response.text:
                data = response.json()
                if data.get('aweme_detail'):
                    return data

                # 如果 ttwid 失效，尝试刷新一次
                if data.get('status_code') == 0 and not data.get('aweme_detail'):
                    logger.info("Douyin API 返回空数据，尝试刷新 ttwid 重试")
                    self._clear_ttwid_cache()
                    self.ttwid = self._get_or_refresh_ttwid(force=True)
                    new_headers['Cookie'] = f"ttwid={self.ttwid}"
                    abogus = self.common_utils.get_abogus(play_url, self.common_utils.user_agent)
                    url = f"{play_url}&a_bogus={abogus}"

                    retry_resp = self.session.get(url, headers=new_headers, verify=False, timeout=10)
                    if retry_resp.status_code == 200:
                        retry_data = retry_resp.json()
                        if retry_data.get('aweme_detail'):
                            return retry_data
        except Exception as e:
            logger.warning(f"Douyin API 请求异常: {e}")

        return None

    # ---------- 方案二：第三方 API 兜底 ----------

    def _try_fallback_api(self):
        """使用公开的第三方解析服务作为兜底"""
        fallback_urls = [
            f"{self.FALLBACK_API}?url={self.real_url}",
        ]
        # 如果有 aweme_id，也尝试直接用 ID
        if self.aweme_id:
            fallback_urls.append(
                f"{self.FALLBACK_API}?url=https://www.douyin.com/video/{self.aweme_id}"
            )

        for fb_url in fallback_urls:
            try:
                resp = requests.get(fb_url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get('code') == 200 and result.get('data'):
                        data = result['data']
                        # 转换为 API 一致的格式
                        return self._normalize_fallback_data(data)
            except Exception as e:
                logger.warning(f"Douyin fallback API 失败 ({fb_url[:60]}): {e}")
                continue

        return None

    def _normalize_fallback_data(self, data):
        """将第三方 API 返回格式映射为标准格式"""
        # bugpk.com 返回格式:
        # { "code": 200, "msg": "解析成功", "data": { "title": "...", "url": "...", "cover": "..." } }
        # 其中 url 是无水印地址
        aweme_detail = {
            "desc": data.get('title', ''),
            "video": {
                "play_addr": {
                    "url_list": [data.get('url', '')]
                },
                "cover": {
                    "url_list": [data.get('cover', '')]
                },
                "dynamic_cover": {
                    "url_list": [data.get('cover', '')]
                }
            },
            "author": {
                "nickname": data.get('author', {}).get('name', '') if isinstance(data.get('author'), dict) else data.get('author', ''),
                "unique_id": str(data.get('author', {}).get('id', '')) if isinstance(data.get('author'), dict) else '',
            }
        }
        return {"aweme_detail": aweme_detail}

    # ---------- Token 管理 ----------

    _TTWID_CACHE = None

    def _get_or_refresh_ttwid(self, force=False):
        """动态获取 ttwid，带类级缓存"""
        if not force and DouyinParser._TTWID_CACHE:
            return DouyinParser._TTWID_CACHE

        try:
            url = "https://ttwid.bytedance.com/ttwid/union/register/"
            post_data = {
                "region": "cn",
                "aid": 6383,
                "need_t": 1,
                "service": "www.douyin.com",
                "migrate_priority": 0,
                "cb_url_protocol": "https",
                "domain": ".douyin.com"
            }
            resp = self.session.post(url, data=json.dumps(post_data), timeout=5)
            ttwid = resp.cookies.get('ttwid')
            if ttwid:
                DouyinParser._TTWID_CACHE = ttwid
                return ttwid
        except Exception as e:
            logger.warning(f"获取 ttwid 失败: {e}")

        # 兜底使用默认值
        default = '1%7CvDWCB8tYdKPbdOlqwNTkDPhizBaV9i91KjYLKJbqurg%7C1723536402%7C314e63000decb79f46b8ff255560b29f4d8c57352dad465b41977db4830b4c7e'
        if force:
            return default
        DouyinParser._TTWID_CACHE = default
        return default

    def _clear_ttwid_cache(self):
        DouyinParser._TTWID_CACHE = None

    def _get_webid(self):
        """获取/生成 webid"""
        return '7307457174287205926'

    # ---------- 数据提取方法 ----------

    def _get_detail(self):
        if not self.data:
            return {}
        return self.data.get('aweme_detail') or {}

    def get_real_video_url(self):
        try:
            detail = self._get_detail()
            if not detail:
                return None
            video = detail.get('video') or {}
            bit_rate = video.get('bit_rate', []) or []
            if bit_rate:
                play_addr_list = bit_rate[0].get('play_addr', {}).get('url_list', []) or []
                if len(play_addr_list) >= 3:
                    return play_addr_list[2]
                return play_addr_list[0] if play_addr_list else None
            # 兜底：从 play_addr 直接取
            play_addr = video.get('play_addr') or {}
            url_list = play_addr.get('url_list', []) or []
            return url_list[0] if url_list else None
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析视频地址失败: {e}")
            return None

    def get_title_content(self):
        try:
            detail = self._get_detail()
            if not detail:
                return None
            return detail.get('desc', '') or None
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析标题失败: {e}")
            return None

    def get_cover_photo_url(self):
        try:
            detail = self._get_detail()
            if not detail:
                return None
            video = detail.get('video') or {}
            # 优先动态封面
            dynamic_cover = video.get('dynamic_cover') or {}
            url_list = dynamic_cover.get('url_list') or []
            if url_list:
                return url_list[0]
            # 其次静态封面
            cover = video.get('cover') or {}
            url_list = cover.get('url_list') or []
            if url_list:
                return url_list[0]
            # 最后图集封面
            images = detail.get('images') or []
            if images:
                first_img = images[0] or {}
                url_list = first_img.get('url_list') or []
                if url_list:
                    return url_list[0]
            return None
        except Exception as e:
            logger.warning(f"解析封面失败: {e}")
            return None

    def get_audio_url(self):
        try:
            detail = self._get_detail()
            if not detail:
                return None
            music = detail.get('music') or {}
            play_url = music.get('play_url') or {}
            url_list = play_url.get('url_list') or []
            return url_list[0] if url_list else None
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析音频失败: {e}")
            return None

    def get_author_info(self):
        try:
            detail = self._get_detail()
            if not detail:
                return None
            author = detail.get('author') or {}
            if not author:
                return None
            avatar_thumb = author.get('avatar_thumb') or {}
            avatar_url_list = avatar_thumb.get('url_list') or [None]
            return {
                "nickname": author.get('nickname', ''),
                "author_id": author.get('unique_id') or author.get('short_id', ''),
                "avatar": avatar_url_list[0]
            }
        except Exception as e:
            logger.warning(f"解析作者信息失败: {e}")
            return None

    def get_image_list(self):
        """抖音图文笔记图片列表"""
        try:
            detail = self._get_detail()
            if not detail:
                return []
            images = detail.get('images') or detail.get('image_list') or []
            image_urls = []
            for img in images:
                if not img:
                    continue
                urls = img.get('url_list') or []
                if urls:
                    img_data = urls[-1]
                    if 'video' in img and 'play_addr' in img.get('video', {}):
                        live_urls = img['video']['play_addr'].get('url_list')
                        if live_urls:
                            img_data = {
                                'url': img_data,
                                'live_photo_url': live_urls[0]
                            }
                    image_urls.append(img_data)
            return image_urls
        except Exception as e:
            logger.warning(f"解析图片列表失败: {e}")
            return []


if __name__ == '__main__':
    test_url = 'https://www.douyin.com/video/7307457174287205926'
    dl = DouyinParser(test_url)
    print("-" * 30)
    print(f"标题: {dl.get_title_content()}")
    print(f"视频: {dl.get_real_video_url()}")
    print(f"封面: {dl.get_cover_photo_url()}")
    print(f"作者: {dl.get_author_info()}")
    print(f"音频: {dl.get_audio_url()}")
    print(f"图片: {len(dl.get_image_list())} 张")
    print("-" * 30)
