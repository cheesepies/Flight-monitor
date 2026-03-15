# ✈️ 东京 ↔ 香港 机票监控

用 **GitHub Actions + fast-flights + Bark** 自动监控往返机票价格，无需任何 API Key，完全免费。

---

## 监控逻辑

每天东京时间 **早 9 点 / 晚 9 点** 自动运行，查询以下 4 个日期组合的往返最低价：

| 去程 | 回程 |
|------|------|
| 8月8日 | 8月15日 |
| 8月8日 | 8月16日 |
| 8月9日 | 8月15日 |
| 8月9日 | 8月16日 |

找出 4 个组合中的**最低总价**，满足以下任一条件时推送 Bark 通知：
- 价格 ≤ 目标价格（¥36,000）
- 刷新历史最低价

---

## 快速配置

### 1. Fork 仓库，推送代码到 GitHub

### 2. 安装 Bark（iPhone）
App Store 搜索 **Bark** → 安装 → 复制 App 内的推送 Key

### 3. 设置 GitHub Secrets
仓库 → Settings → Secrets and variables → Actions → New repository secret

| 名称 | 内容 | 必填 |
|------|------|------|
| `BARK_KEY` | Bark App 里的 Key | ✅ |
| `BARK_URL` | 自建 Bark 服务器地址 | 默认 `https://api.day.app` |

### 4. 启用 Actions
仓库 → Actions → 点击 Enable workflow → 手动 Run workflow 测试

---

## 修改配置

编辑 `monitor.py` 顶部：

```python
OUTBOUND_DATES = ["2025-08-08", "2025-08-09"]   # 可接受的去程日期
INBOUND_DATES  = ["2025-08-15", "2025-08-16"]   # 可接受的回程日期
TARGET_PRICE   = 36000                           # 目标总价（日元）
```

---

## 推送通知示例

```
✈️ 东京↔香港 ¥34,500

2025-08-08 去 / 2025-08-15 回
Cathay Pacific · 直飞
低于目标价 ¥36,000 · 价格偏低🟢
```

---

## 注意事项

- `fast-flights` 通过 Google Flights 公开接口获取数据，价格为**美元**，程序自动实时换算为**日元**
- 价格基于 Google 服务器 IP，与日本本地浏览器看到的价格可能略有差异，但变化趋势一致
- 历史价格保存在 `price_history.json`，每次运行后自动提交到仓库
