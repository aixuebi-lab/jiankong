import time
import requests
from web3 import Web3

# ==================== 配置区 ====================
WALLET_ADDRESS = "0xcca208372204416762dabe99eb0138b5cdff868d"

# MegaNode 专属RPC地址（从仪表盘获取）
# 格式类似：https://bsc-mainnet.nodereal.io/v1/你的大串密钥ID
BSC_RPC = "https://bsc-mainnet.nodereal.io/v1/d3cf00af6c9e434ca5f81d36ff42c810"

# 钉钉机器人Webhook地址
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=383e7ddda0409845a782ae795c789f27533fca26221f300d28a47dd83f720a75"

# 监控间隔（秒），建议30秒以上，避免频繁请求
CHECK_INTERVAL = 30

# ==================== 初始化 ====================
w3 = Web3(Web3.HTTPProvider(BSC_RPC))
if not w3.is_connected():
    raise Exception("MegaNode RPC连接失败，请检查地址和网络")

# 校验钱包地址格式
try:
    WALLET_ADDRESS = Web3.to_checksum_address(WALLET_ADDRESS)
except Exception:
    raise Exception("钱包地址格式不正确")

print(f"✅ 已连接MegaNode，开始监控钱包: {WALLET_ADDRESS}")

# 存储上一次的BNB余额（单位：wei）
last_balance_wei = 0
# 存储上一次的交易数量，用于判断是否有新交易
last_tx_count = 0


# ==================== 钉钉推送函数 ====================
def send_dingtalk_message(text, msg_type="text"):
    """发送钉钉消息，支持text和markdown类型"""
    headers = {"Content-Type": "application/json;charset=utf-8"}
    if msg_type == "markdown":
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "钱包监控告警",
                "text": text
            }
        }
    else:
        data = {
            "msgtype": "text",
            "text": {"content": text}
        }
    
    try:
        resp = requests.post(DINGTALK_WEBHOOK, json=data, headers=headers, timeout=10)
        print(f"📨 钉钉推送状态: {resp.status_code}")
        if resp.status_code != 200:
            print(f"响应内容: {resp.text}")
    except Exception as e:
        print(f"❌ 钉钉推送失败: {e}")


# ==================== 链上查询函数 ====================
def get_bnb_balance(address):
    """获取BNB余额，返回wei单位"""
    try:
        return w3.eth.get_balance(address)
    except Exception as e:
        print(f"⚠️ 查询余额失败: {e}")
        return None


def get_transaction_count(address):
    """获取钱包的非交易数量（nonce），用于判断是否有新交易发出"""
    try:
        return w3.eth.get_transaction_count(address)
    except Exception as e:
        print(f"⚠️ 查询交易数量失败: {e}")
        return None


def get_latest_transactions(address, limit=5):
    """
    获取钱包最近N笔交易（仅限对外发送的交易）
    注意：此方法通过遍历区块获取，对于高频钱包可能较慢
    更推荐使用BSCTrace API查询，这里提供一个简化版
    """
    try:
        # 获取当前区块号
        current_block = w3.eth.block_number
        txs = []
        # 从最新区块往前查，最多查20个区块，找到5笔交易为止
        for block_num in range(current_block, max(current_block - 20, 0), -1):
            block = w3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                # 筛选出发送方或接收方是该地址的交易
                if tx['from'].lower() == address.lower() or (tx.get('to') and tx['to'].lower() == address.lower()):
                    # 格式化交易信息
                    tx_info = {
                        'hash': tx['hash'].hex(),
                        'from': tx['from'],
                        'to': tx.get('to'),
                        'value': w3.from_wei(tx['value'], 'ether'),
                        'block': block_num,
                        'gas_price': w3.from_wei(tx.get('gas_price', 0), 'gwei')
                    }
                    txs.append(tx_info)
                    if len(txs) >= limit:
                        return txs
        return txs
    except Exception as e:
        print(f"⚠️ 查询交易记录失败: {e}")
        return []


# ==================== 监控主逻辑 ====================
def main():
    global last_balance_wei, last_tx_count
    
    print("🔄 开始监控循环...")
    
    while True:
        try:
            # 1. 查询当前余额
            current_balance_wei = get_bnb_balance(WALLET_ADDRESS)
            if current_balance_wei is None:
                print("⏳ 余额查询失败，等待重试...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            current_balance_ether = w3.from_wei(current_balance_wei, 'ether')
            
            # 2. 查询当前交易数量
            current_tx_count = get_transaction_count(WALLET_ADDRESS)
            if current_tx_count is None:
                current_tx_count = last_tx_count  # 查询失败则跳过
            
            # 3. 判断是否需要告警
            alert_messages = []
            
            # 3.1 余额变化告警（首次运行不告警）
            if last_balance_wei != 0 and current_balance_wei != last_balance_wei:
                change_wei = current_balance_wei - last_balance_wei
                change_ether = w3.from_wei(abs(change_wei), 'ether')
                direction = "转入" if change_wei > 0 else "转出"
                
                msg = (
                    f"🔔 **钱包余额变动告警**\n\n"
                    f"📌 地址: `{WALLET_ADDRESS}`\n"
                    f"📊 变动: {direction} **{change_ether:.6f} BNB**\n"
                    f"💰 当前余额: **{current_balance_ether:.6f} BNB**"
                )
                alert_messages.append(("markdown", msg))
                print(f"💰 余额变动: {direction} {change_ether:.6f} BNB")
            
            # 3.2 交易数量变化告警（说明有新的链上操作）
            if last_tx_count != 0 and current_tx_count != last_tx_count:
                tx_diff = current_tx_count - last_tx_count
                msg = f"🔔 **钱包发生新交易**\n\n📌 地址: `{WALLET_ADDRESS}`\n📊 累计交易数: {last_tx_count} → {current_tx_count}（新增 {tx_diff} 笔）"
                alert_messages.append(("markdown", msg))
                print(f"📝 新交易: {last_tx_count} → {current_tx_count}")
                
                # 可选：打印最近3笔交易详情
                recent_txs = get_latest_transactions(WALLET_ADDRESS, limit=3)
                if recent_txs:
                    detail = "\n\n📋 **最近交易**:\n"
                    for tx in recent_txs:
                        detail += f"- {tx['hash'][:10]}... | {tx['value']:.4f} BNB | → {tx['to'][:10]}...\n"
                    alert_messages.append(("markdown", detail))
            
            # 4. 更新状态
            last_balance_wei = current_balance_wei
            last_tx_count = current_tx_count
            
            # 5. 如果有告警，发送钉钉
            if alert_messages:
                # 合并所有告警内容（避免频繁推送）
                combined_msg = ""
                for msg_type, content in alert_messages:
                    combined_msg += content + "\n---\n"
                send_dingtalk_message(combined_msg, "markdown")
            else:
                # 首次运行或没有变化，仅打印日志
                if last_balance_wei == 0:
                    print(f"📊 初始余额: {current_balance_ether:.6f} BNB, 交易数: {current_tx_count}")
                else:
                    print(f"⏱️ {time.strftime('%H:%M:%S')} 余额: {current_balance_ether:.6f} BNB, 交易数: {current_tx_count}")
            
            # 6. 等待下一次检查
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n🛑 监控已停止")
            break
        except Exception as e:
            print(f"❌ 循环异常: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
