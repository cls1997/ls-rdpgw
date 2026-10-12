# ls-rdpgw

基于 LinuxServer Debian Bookworm 和 s6-overlay 的远程桌面网关镜像。
网关源码来自固定提交的 [cls1997/rdpgw](https://github.com/cls1997/rdpgw) 子模块。

## 构建

```sh
git clone --recurse-submodules https://github.com/cls1997/ls-rdpgw.git
cd ls-rdpgw
# 已克隆仓库可运行：git submodule update --init --recursive
docker build --platform linux/amd64 -t ls-rdpgw:local .
```

## 运行与首次配置

```sh
mkdir -p config
docker run -d --name rdpgw \
  -e PUID=1000 -e PGID=1000 \
  -p 443:443 \
  -v "$(pwd)/config:/config" \
  ls-rdpgw:local
```

首次启动生成带中文注释的 `config/rdpgw.yaml`，随机生成六个独立的
32 字符密钥，并以 0600 权限保存。已有配置不会被覆盖或重新生成密钥。
首次配置仍有 `CHANGE_ME` 占位值时初始化失败，日志提示修改配置。
设置网关域名、允许连接的桌面地址以及 OpenID Connect issuer、客户端 ID
和客户端密钥后，运行 `docker restart rdpgw`。
认证服务的回调地址应为 `https://你的网关域名/callback`。

默认使用 OpenID Connect、443 端口和 TLS。镜像内的自签名证书仅用于测试，
生产部署应将受信任证书和私钥放入 `/config`，修改 `Server.CertFile` 和
`Server.KeyFile`，并确保运行用户有读取权限。Windows 客户端要求可信证书。
默认后端必须明确列入 `Server.Hosts`。

使用前置 TLS 代理时可以设置 `Server.Tls: disable` 并调整端口及端口映射。
`Server.Tls: auto` 可使用 ACME，需要额外开放并映射 80 端口。
上游支持 `RDPGW_SERVER__PORT`、`RDPGW_SERVER__TLS` 等环境变量覆盖配置；
初始化校验及就绪检查也读取这些覆盖值。

非 root 模式需提前确保挂载目录和配置对运行用户可写/可读，并给予绑定低端口
所需权限或改用高端口。PAM/local 认证需要另行部署 `rdpgw-auth` 与 PAM 配置，
本镜像不会自动启动该认证服务。

## 机器列表与连接页面

启用 OIDC 后访问 `https://你的网关域名/`，登录后显示有效 `Server.Hosts`
中的机器列表。点击连接下载 `.rdp` 文件，用本地远程桌面客户端打开。
高级选项允许自定义桌面用户名、域、提示输入凭据、全屏/窗口、分辨率、
多显示器、剪贴板、磁盘、打印机及音频。密码在客户端输入，页面不保存这些选项。
自定义桌面账户绕过 `Client.UsernameTemplate` 和桌面用户令牌拼接，
但网关令牌仍使用 OIDC 登录身份；留空用户名或域会清空模板对应字段。
没有修改的选项继续沿用 `Client.Defaults` 和现有默认值。

状态由网关探测目标 RDP TCP 端口：明确配置为 `desktop:3390` 时探测 3390，
仅在省略端口时使用 3389。域名、IPv4 和 IPv6 使用同一套地址解析和校验。
每次连接探测超时 2 秒，最多并发 8 个，结果缓存 15 秒；页面每 15 秒刷新状态，
也可手动刷新。在线仅代表端口可达，不代表账户已验证；不可达仍允许尝试连接。
页面隐藏时暂停轮询，登录过期时提示重新登录。未启用 OIDC 时不提供此页面。

连接继续使用原有 GET `/connect`，例如：

```text
/connect?host=desktop%3A3390&credential_mode=custom&username=alice&domain=CONTOSO&fullscreen=0&width=1280&height=720&clipboard=0
```

| 参数 | 可选值 |
| --- | --- |
| `host` | `Server.Hosts` 中的原始条目；模板条目也传原值 |
| `credential_mode` | `default`（默认）或 `custom` |
| `username`、`domain` | 自定义桌面账户，仅在 `custom` 模式使用，最长 256 字节，可为空 |
| `prompt_credentials`、`fullscreen`、`multimon` | `0` 或 `1` |
| `width`、`height` | 200–8192 |
| `clipboard`、`drives`、`printers` | `0` 或 `1`；启用受网关 Caps 限制 |
| `audiomode` | `0` 本地播放、`1` 远程播放、`2` 关闭 |

参数省略时沿用服务器设置，OIDC 回调保留原连接参数。
`roundrobin` 有 `host` 时校验列表并指定机器，无 `host` 时保留随机选择；
`unsigned`、`any`、`signed` 保留已有选机规则。首页始终只列出配置内目标，
`signed` 模式需使用既有签名链接，首页暂不提供直接选机连接。
网关日志不记录查询参数；连接文件和首页禁止缓存。

本功能以 [patches/landing.patch](patches/landing.patch) 交付，Docker 构建时应用到
固定子模块源码，不需要 nginx、新的连接接口或 JSON API。更新子模块版本后，
应先重新验证补丁；无法应用或测试失败时镜像构建直接失败。
配置变更仍需要重启容器。

## 就绪检查

s6 就绪检查按有效配置访问本机 `/metrics`，要求 HTTP 200。
`Tls: disable` 使用 HTTP，`enable` 和 `auto` 使用 HTTPS；请求超时为 3 秒，
不使用代理或跟随重定向。仅本机 HTTPS 探测跳过证书校验，不影响客户端 TLS。
配置格式错误、无效端口、服务未监听或错误状态码都会检查失败。

```sh
docker exec rdpgw /etc/s6-overlay/s6-rc.d/svc-rdpgw/data/check
```

GitHub Actions 构建 amd64 镜像并按既有规则发布到 GHCR，手动运行可禁用推送。

## 验证

安装 Python 3、PyYAML 和 OpenSSL 后运行：

```sh
python3 -m unittest discover -s tests -v
```

测试会临时监听本机随机端口，验证配置初始化、占位值校验、环境变量覆盖、
HTTP/HTTPS 探测及失败场景。

安装 Go 1.22+ 和 patch 后，可在临时源码副本中应用同一份补丁并测试，
不会改写子模块：

```sh
tests/test_landing.sh
```

该检查覆盖机器地址与端口解析、TCP 探测、缓存及并发限制、RDP 参数覆盖、
网关身份隔离，以及使用模拟 OIDC 服务完成登录回调和连接文件下载。
Docker 构建也运行同一套 Go 测试。

完整容器启动验证（需要 Docker）：

```sh
docker build --platform linux/amd64 -t ls-rdpgw:verify .
python3 tests/smoke_container.py
# 验证其他本地镜像标签时：
# RDPGW_TEST_IMAGE=ls-rdpgw:landing-verify python3 tests/smoke_container.py
```

该测试使用容器内的模拟 OIDC discovery 服务，验证配置保留、只读目录报错、
PUID/PGID、TLS 启动、s6 就绪、首页与连接认证跳转和 PAM 动态库加载；
不验证真实用户登录或 RDP 桌面会话。
临时容器在测试结束后删除。
