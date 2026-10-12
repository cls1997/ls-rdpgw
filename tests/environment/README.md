# 使用现有 SSO 和桌面后端的本地测试环境

测试网关默认使用仓库构建的 `ls-rdpgw:verify` 镜像，可通过 `RDPGW_TEST_IMAGE`
选择其他本地镜像。已有真实配置位于
`.local/rdpgw-test/config/rdpgw.yaml`，被 Git 和 Docker 构建上下文忽略。
该私有目录不会随 Git 克隆；新机器需自行提供配置。

在仓库根目录运行：

```sh
# 已准备好本地镜像时无需重新构建。
docker compose -f tests/environment/compose.yaml up -d
# 使用已构建的 landing 测试镜像：
RDPGW_TEST_IMAGE=ls-rdpgw:landing-verify docker compose -f tests/environment/compose.yaml up -d --no-build
# 修改源码后：
docker compose -f tests/environment/compose.yaml up -d --build
# 查看状态与日志：
docker compose -f tests/environment/compose.yaml ps
docker compose -f tests/environment/compose.yaml logs --tail 100 rdpgw
# 停止，保留本地配置：
docker compose -f tests/environment/compose.yaml down
```

## 入口和反向代理

- 容器内部：HTTP 8080；宿主机：HTTP 18080，默认监听所有地址以供现有代理访问。
- 本机检查：`http://localhost:18080/metrics`。
- Landing 页面：`https://home.kachitoritai.run:9999/`。
- 原有连接入口：`https://home.kachitoritai.run:9999/connect`。
- SSO 回调：`https://home.kachitoritai.run:9999/callback`，需在认证服务中登记。
- 允许的远程桌面后端：以 `.local/rdpgw-test/config/rdpgw.yaml` 的 `Server.Hosts` 为准。

当前宿主机局域网 IP 为 `10.10.0.157`。
将现有 HTTPS 反向代理上游指向 `http://10.10.0.157:18080`。
代理在本机时也可用 `http://127.0.0.1:18080`。
保留 Host，正确设置 X-Forwarded-For，并支持网关协议使用的长连接、
RDG_IN_DATA/RDG_OUT_DATA 请求方法和 WebSocket 升级；关闭请求/响应缓冲。
保持外部 HTTPS 入口的证书受客户端信任。

如只需要本机代理，可在启动命令前设置 `RDPGW_TEST_BIND=127.0.0.1`；
用 `RDPGW_TEST_PORT` 修改宿主机端口，容器内仍为 8080。
运行用户可通过 `RDPGW_TEST_UID` 和 `RDPGW_TEST_GID` 调整。

## 配置处理与验收

保留提供的认证、后端、已有密钥与用户名模板。仅将 GatewayAddress 补为完整
HTTPS URL，新增持久化 PAATokenEncryptionKey，并创建缺失的 default.rdp。
网关地址和后端信息会由网关覆盖 RDP 模板对应字段。

先确认容器 healthy，再通过外部 `/connect` 完成 SSO 登录并下载 RDP 文件。
下载文件应包含外部网关地址和指定后端；用 RDP 客户端打开进行桌面连接测试。
不要把本机 HTTP 地址作为正式登录入口，OIDC 回调使用配置中的外部域名。

保留配置中的 `Client.UsernameTemplate` 和 `Security.EnableUserToken`。
用户名模板包含用户令牌时，后端需支持对应认证机制；普通 Windows 密码账户
可使用 `{{ username }}` 并关闭 EnableUserToken。不能只凭网关就绪判断桌面登录成功。

`VerifyClientIp: true` 保持原值；浏览器登录与 RDP 连接经过代理后应得到一致的
客户端 IP。环境包含 NAT 或多层代理时，先核对 X-Forwarded-For 与实际流量。

## Landing 测试实例（2026-10-12）

- 使用 `RDPGW_TEST_IMAGE=ls-rdpgw:landing-verify` 启动现有 Compose 测试实例。
- 容器 `ls-rdpgw-test-rdpgw-1` 为 healthy，s6 ready；`/metrics` 返回 200。
- `.local/rdpgw-test/config/rdpgw.yaml` 启动前后 SHA-256 一致，配置未改写。
- 本机 HTTP 18080 的首页和 `/connect` 均返回 302，回调地址保持为
  `https://home.kachitoritai.run:9999/callback`。
- 外部 `https://home.kachitoritai.run:9999/` 返回 302，正确跳转至配置的 SSO。
- 启动检查时，从容器可连接当时配置的后端 `10.10.0.157:3389` TCP 端口。
- 尚未进行真实用户登录和桌面会话验证；通过上述外部首页登录后可查看机器列表。

## 此前检查记录

- 网关 HTTP `/metrics` 返回 200，Docker healthy。
- `/connect` 返回 302，跳转至提供的 SSO，redirect_uri 为
  `https://home.kachitoritai.run:9999/callback`。
- 容器和宿主机均无法连接 `10.10.0.66:3389`，返回 No route to host；
  宿主机邻居表对该 IP 显示 FAILED。需先确认后端开机、地址和局域网连通性，
  再检查 RDP 服务与防火墙。
- 尚未完成用户 SSO 登录或真实 RDP 会话；外部反向代理由部署者转发后测试。

## RDG 数据通道诊断

```sh
python3 tests/environment/probe_transport.py
```

该脚本比较本机 18080 与外部 HTTPS 9999 的 RDG 初始握手，不提交用户凭据，
不建立已认证的桌面会话。它在初始 HTTP 响应后继续发送 RDG 数据，验证数据流
是否被代理保留。每个连接超时 5 秒，测试结束关闭连接。

本次复现结果：本机直连收到 18 字节 HANDSHAKE_RESPONSE；群晖反向代理路径
收到初始 HTTP 200 后，后续 RDG 握手超时。Windows 实际连接日志同样显示
RDGIN/RDGOUT 建立后读取数据流失败，尚未进入 Tunnel create 或后端连接阶段。
SSO 已认证成功，因此这次卡住的位置在代理路径的 RDG 传输阶段。

建议用支持 RDG 数据流的代理配置，或采用 TCP 透传并在 rdpgw 端启用 TLS。
后者需给网关提供客户端信任的证书，并同步调整监听端口和健康检查；当前
仍保留 HTTP 配置，尚未更改群晖或部署 TLS 直连入口。
