# Content Hive Plugin: 抖音

一个用于Content Hive的抖音内容解析插件。通过解析抖音链接，提取视频内容、作者信息等数据。

Plugin for [Content Hive](https://github.com/content-hive/content-hive).

## Layout

```
plugin/              # plugin source, installed as plugins/douyin/ by Content Hive
├── manifest.json    # plugin metadata (domain, version, requirements, release_notes)
├── __init__.py
└── ...
contenthive.json     # repository metadata for the Content Hive plugin catalog
```

## Requirements

- `gmssl>=3.2.2`

Installed automatically by Content Hive from `manifest.json`.

## Disclaimer

> 本插件通过解析抖音链接获取内容，需要配置账号 Cookie 以访问受保护内容，存在账号被封禁的风险。使用前请确保符合抖音服务条款及当地法律法规，并自行承担相关风险。平台规则变更可能导致插件失效。
