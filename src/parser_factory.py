from src.parsers.xiaohongshu_parser import XiaohongshuParser
from src.parsers.douyin_parser import DouyinParser
from src.parsers.kuaishou_parser import KuaishouParser
from src.parsers.bilibili_parser import BilibiliParser


class ParserFactory:
    platform_to_parser = {
        "小红书": XiaohongshuParser,
        "抖音": DouyinParser,
        "快手": KuaishouParser,
        "哔哩哔哩": BilibiliParser,
    }

    @staticmethod
    def create_parser(platform, real_url):
        parser_class = ParserFactory.platform_to_parser.get(platform)
        return parser_class(real_url)
