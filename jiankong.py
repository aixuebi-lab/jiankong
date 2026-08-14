import os
import time
import requests
from web3 import Web3

# ====== 安装依赖 ======
os.system("pip install web3 requests -q")

# ====== 配置区 ======
WALLET_ADDRESS = "0xCca208372204416762dABE99Eb0138b5cdfF868D"
BSC_RPC = "https://bsc-mainnet.nodereal.io/v1/d3cf00af6c9e434ca5f81d36ff42c810"
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=383e7ddda0409845a782ae795c789f27533fca26221f300d28a47dd83f720a75"
CHECK_INTERVAL = 30  # 每30秒检查一次

# H 代币合约地址
H_TOKEN_ADDRESS = "0x44f161ae29361e332dea039dfa2f404e0bc5b5cc"
# ===================================

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
if not w3.is_connected():
    print("RPC连接失败")
    exit()

WALLET_ADDRESS = Web3.to_checksum_address(WALLET_ADDRESS)
H_TOKEN_ADDRESS = Web3.to_checksum_address(H_TOKEN_ADDRESS)

# H 代币合约 ABI（包含 Transfer 事件）
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
# 上次检查的区块号
last_block = w3.eth.block_number

while True:
    try:
        current_block = w3.eth.block_number

        # 每次最多往前查 100 个区块
        from_block = max(last_block - 100, 0)
        to_block = current_block

        # 获取 H 代币的 Transfer 事件
        events = h_token_contract.events.Transfer.get_logs(
            from_Block=from_block,
            to_Block=to_block
        )

        for event in events:
            tx_hash = event['transactionHash'].hex()
            
            # 如果已经处理过，跳过
            if tx_hash in processed_txs:
                continue

            from_addr = event['args']['from'].lower()
            to_addr = event['args']['to'].lower()
            value = event['args']['value']
            value_h = format_h(value)

            # 只关注涉及监控钱包的交易
            wallet_lower = WALLET_ADDRESS.lower()
            
            if from_addr == wallet_lower:
                # 钱包转出 H = 卖出
                msg = f"🔴 H 卖出\n地址: {WALLET_ADDRESS}\n卖出: {value_h:.4f} H\n交易: https://bscscan.com/tx/{tx_hash}"
                send_dingtalk(msg)
                print(f"[卖出] {value_h:.4f} H")
                processed_txs.add(tx_hash)
                
            elif to_addr == wallet_lower:
                # 钱包转入 H = 买入
                msg = f"🟢 H 买入\n地址: {WALLET_ADDRESS}\n买入: {value_h:.4f} H\n交易: https://bscscan.com/tx/{tx_hash}"
                send_dingtalk(msg)
                print(f"[买入] {value_h:.4f} H")
                processed_txs.add(tx_hash)

        # 更新区块号
        last_block = current_block
        print(f"{time.strftime('%H:%M:%S')} 检查到区块 {current_block}，已监控 {len(processed_txs)} 笔交易")

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print(f"错误: {e}")
        time.sleep(CHECK_INTERVAL)
