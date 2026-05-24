import unittest

from download_extractor import extract_download_buttons


DOWNLOAD_SNIPPETS = """
<div class="btn-group">
    <a target="_blank" href="https://daoyu.fan/goto?down=a0M5cm5keE83OFBXa29qQzJFakpGeXRiTUYrREJNVmM" class="btn btn-success" rel="nofollow noopener noreferrer"><i class="fas fa-cloud-download-alt me-1"></i>在线观看版本--先保存-再在网盘app里在线观看-一点也不卡</a>
</div>
<div class="btn-group">
    <a target="_blank" href="https://daoyu.fan/goto?down=NkI5c29ETDBIVlhXa29qQzJFakpGeXRiTUYrREJNVmM" class="btn btn-success" rel="nofollow noopener noreferrer"><i class="fas fa-cloud-download-alt me-1"></i>压缩包版本-提示需要会员去网盘app新人活动领几百G先再保存</a>
    <button type="button" class="user-select-all copy-pwd btn btn-success opacity-75" data-pwd="weimi.life" title="weimi.life">密码<i class="far fa-copy ms-1"></i></button>
</div>
"""


class DownloadExtractorTest(unittest.TestCase):
    def test_extracts_download_links_and_optional_passwords(self):
        buttons = extract_download_buttons(DOWNLOAD_SNIPPETS)

        self.assertEqual(
            buttons,
            [
                {
                    "href": "https://daoyu.fan/goto?down=a0M5cm5keE83OFBXa29qQzJFakpGeXRiTUYrREJNVmM",
                    "text": "在线观看版本--先保存-再在网盘app里在线观看-一点也不卡",
                    "password": None,
                },
                {
                    "href": "https://daoyu.fan/goto?down=NkI5c29ETDBIVlhXa29qQzJFakpGeXRiTUYrREJNVmM",
                    "text": "压缩包版本-提示需要会员去网盘app新人活动领几百G先再保存",
                    "password": "weimi.life",
                },
            ],
        )

    def test_ignores_unrelated_button_groups(self):
        html = """
        <div class="btn-group">
            <a href="https://example.com/not-download">普通链接</a>
        </div>
        """

        self.assertEqual(extract_download_buttons(html), [])


if __name__ == "__main__":
    unittest.main()
