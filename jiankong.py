import os
import time
import requests
from web3 import Web3

# ====== 安装依赖 ======
os.system("pip install web3 requests -q")

# ====== 配置区（改成你自己的） ======
WALLET_ADDRESS = "0xCca208372204416762dABE99Eb0138b5cdfF868D"

# 币安官方公共节点列表（支持故障转移）
BSC_RPC_LIST = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/"
]

DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=383e7ddda0409845a782ae795c789f27533fca26221f300d28a47dd83f720a75"
CHECK_INTERVAL = 10  # 检查间隔（秒）

# H 代币合约地址
H_TOKEN_ADDRESS = "0x44f161ae29361e332dea039dfa2f404e0bc5b5cc"
# ===================================

# 初始化 Web3 连接（带故障转移）
w3 = None
current_rpc_index = 0

for i, rpc in enumerate(BSC_RPC_LIST):
    try:
        test_w3 = Web3(Web3.HTTPProvider(rpc))
        if test_w3.is_connected():
            w3 = test_w3
            current_rpc_index = i
            print(f"✅ 成功连接到 RPC: {rpc}")
            break
    except:
        continue

if w3 is None:
    print("❌ 所有 RPC 节点连接失败，请检查网络")
    exit()

def switch_rpc():
    """切换到下一个可用的 RPC 节点"""
    global w3, current_rpc_index
    for i in range(len(BSC_RPC_LIST)):
        idx = (current_rpc_index + 1 + i) % len(BSC_RPC_LIST)
        try:
            test_w3 = Web3(Web3.HTTPProvider(BSC_RPC_LIST[idx]))
            if test_w3.is_connected():
                w3 = test_w3
                current_rpc_index = idx
                print(f"🔄 已切换到 RPC: {BSC_RPC_LIST[idx]}")
                return True
        except:
            continue
    return False

WALLET_ADDRESS = Web3.to_checksum_address(WALLET_ADDRESS)
H_TOKEN_ADDRESS = Web3.to_checksum_address(H_TOKEN_ADDRESS)

# H 代币合约 ABI
H_TOKEN_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

h_token_contract = w3.eth.contract(address=H_TOKEN_ADDRESS, abi=H_TOKEN_ABI)

# 获取 H 代币精度
try:
    H_DECIMALS = h_token_contract.functions.decimals().call()
except:
    H_DECIMALS = 18

def format_h(wei_amount):
    return wei_amount / (10 ** H_DECIMALS)

def send_dingtalk(text):
    try:
        requests.post(DINGTALK_WEBHOOK, json={"msgtype": "text", "text": {"content": text}}, timeout=10)
    except:
        pass

print(f"开始监控钱包: {WALLET_ADDRESS}")
print(f"监控代币 H: {H_TOKEN_ADDRESS}")
print("等待新交易...")

# 记录已处理过的交易哈希，避免重复告警
processed_txs = set()
last_block = w3.eth.block_number

while True:
    try:
        current_block = w3.eth.block_number
        from_block = max(last_block - 100, 0)
        to_block = current_block

        # 获取 H 代币的 Transfer 事件
        events = h_token_contract.events.Transfer.get_logs(
            from_block=from_block,
            to_block=to_block
        )

        for event in events:
            tx_hash = event['transactionHash'].hex()
            
            if tx_hash in processed_txs:
                continue

            from_addr = event['args']['from'].lower()
            to_addr = event['args']['to'].lower()
            value = event['args']['value']
            value_h = format_h(value)

            wallet_lower = WALLET_ADDRESS.lower()
            
            if from_addr == wallet_lower:
                msg = f"🔴 H 卖出\n地址: {WALLET_ADDRESS}\n卖出: {value_h:.4f} H\n交易: https://bscscan.com/tx/{tx_hash}"
                send_dingtalk(msg)
                print(f"[卖出] {value_h:.4f} H")
                processed_txs.add(tx_hash)
                
            elif to_addr == wallet_lower:
                msg = f"🟢 H 买入\n地址: {WALLET_ADDRESS}\n买入: {value_h:.4f} H\n交易: https://bscscan.com/tx/{tx_hash}"
                send_dingtalk(msg)
                print(f"[买入] {value_h:.4f} H")
                processed_txs.add(tx_hash)

        last_block = current_block
        print(f"{time.strftime('%H:%M:%S')} 检查到区块 {current_block}，已监控 {len(processed_txs)} 笔交易")

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print(f"⚠️ 错误: {e}")
        
        # 尝试切换 RPC 节点
        if "connection" in str(e).lower() or "timeout" in str(e).lower():
            print("🔄 尝试切换 RPC 节点...")
            if switch_rpc():
                # 更新合约实例
                h_token_contract = w3.eth.contract(address=H_TOKEN_ADDRESS, abi=H_TOKEN_ABI)
                try:
                    H_DECIMALS = h_token_contract.functions.decimals().call()
                except:
                    H_DECIMALS = 18
                print("✅ RPC 切换成功，继续监控")
            else:
                print("❌ 所有 RPC 节点均不可用，等待重试...")
        
        time.sleep(CHECK_INTERVAL * 2)  # 出错后等待更长时间
