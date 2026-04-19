import math
from constants import (
    STREAMLIT_CRASH_USERS,
    STREAMLIT_DB_OVERLOAD_USERS,
    STREAMLIT_DB_MAX_CONNECTIONS,
    AWS_SCALE_THRESHOLD_CPU,
    AWS_MAX_INSTANCES,
    AWS_SCALE_DELAY_STEPS,
    AWS_DB_MAX_REPLICAS,
    AWS_DB_SCALE_THRESHOLD,
    AWS_DB_SCALE_DELAY_STEPS,
)


def ramp_up(target: int, step: int, total: int) -> int:
    """sigmoid曲線でアクセス数を徐々に増加させる"""
    # sigmoid: 0→1 を step/total で進める。中間点(total*0.4)で急増
    x = (step / total - 0.4) * 10
    ratio = 1 / (1 + math.exp(-x))
    return int(target * ratio)


def compute_streamlit_state(users: int) -> dict:
    """
    Streamlit Cloud の状態を計算する。

    Returns:
        dict with keys:
            cpu (float): CPU使用率 %
            memory (float): メモリ使用率 %
            response_time (float): 応答時間 秒
            current_users (int): 現在のアクセス数
            is_crashed (bool): クラッシュ状態か
    """
    # CPU: 3000人で100%到達
    cpu = min(users / (STREAMLIT_CRASH_USERS * 0.03), 100.0)

    # メモリ: 4000人で100%到達
    memory = min(users / (STREAMLIT_CRASH_USERS * 0.04), 100.0)

    # 応答時間: 指数的に悪化（1000人で約2秒、2000人で約8秒）
    response_time = 0.2 + (users / 1000) ** 2 * 0.2

    # クラッシュ判定
    is_crashed = users >= STREAMLIT_CRASH_USERS

    if is_crashed:
        cpu = 100.0
        memory = 100.0
        response_time = float("inf")

    # DB: クエリ時間（指数的悪化。2000人超で急増、クラッシュ時はタイムアウト）
    db_query_ms = 20 + (users / 300) ** 2.5
    db_connections = min(int(users * 0.15), STREAMLIT_DB_MAX_CONNECTIONS)
    db_overloaded = users >= STREAMLIT_DB_OVERLOAD_USERS

    if is_crashed:
        db_query_ms = float("inf")
        db_connections = STREAMLIT_DB_MAX_CONNECTIONS

    return {
        "cpu": cpu,
        "memory": memory,
        "response_time": response_time,
        "current_users": users,
        "is_crashed": is_crashed,
        "db_query_ms": db_query_ms,
        "db_connections": db_connections,
        "db_overloaded": db_overloaded,
    }


def compute_aws_state(
    users: int,
    current_instances: int,
    scale_cooldown: int,
    db_replicas: int,
    db_scale_cooldown: int,
) -> tuple:
    """
    AWS / Azure の状態を計算する。オートスケーリングとDBレプリカスケールも処理。

    Args:
        users: 現在のアクセス数
        current_instances: 現在のインスタンス数
        scale_cooldown: スケールアウトまでの残りステップ数（0のとき発動可能）
        db_replicas: 現在のリードレプリカ数
        db_scale_cooldown: レプリカ追加のクールダウン残ステップ数

    Returns:
        (state_dict, new_instances, new_scale_cooldown, new_db_replicas, new_db_scale_cooldown)
        state_dict keys:
            cpu_per_instance (float): 1台あたりのCPU使用率 %
            response_time (float): 応答時間 秒
            current_users (int): 現在のアクセス数
            instances (int): 稼働インスタンス数
            scale_event (str | None): スケールアウトイベントメッセージ
            db_replicas (int): 現在のリードレプリカ数
            db_query_ms (float): クエリ時間 ms
            db_load_per_replica (float): レプリカ1台あたりのDB負荷 %
            db_scale_event (str | None): レプリカ追加のイベントメッセージ
    """
    new_instances = current_instances
    new_cooldown = max(scale_cooldown - 1, 0)
    scale_event = None

    # 1台あたりのCPU使用率
    cpu_per_instance = min(users / (current_instances * 30), 100.0)

    # EC2スケールアウト判定
    if (
        cpu_per_instance > AWS_SCALE_THRESHOLD_CPU
        and new_instances < AWS_MAX_INSTANCES
        and new_cooldown == 0
    ):
        new_instances = min(current_instances + 1, AWS_MAX_INSTANCES)
        new_cooldown = AWS_SCALE_DELAY_STEPS
        scale_event = f"{current_instances}台 → {new_instances}台 にスケールアウト"
        cpu_per_instance = min(users / (new_instances * 30), 100.0)

    # 応答時間: 台数増加に比例して安定
    response_time = 0.2 + (users / (new_instances * 3000)) * 0.8
    response_time = min(response_time, 5.0)

    # DB: レプリカ1台あたりの負荷（読み取り分散）
    new_db_replicas = db_replicas
    new_db_cooldown = max(db_scale_cooldown - 1, 0)
    db_scale_event = None

    db_load_per_replica = min(users / (db_replicas * 4000) * 100, 100.0)

    # DBレプリカスケールアウト判定
    if (
        db_load_per_replica > AWS_DB_SCALE_THRESHOLD
        and new_db_replicas < AWS_DB_MAX_REPLICAS
        and new_db_cooldown == 0
    ):
        new_db_replicas = min(db_replicas + 1, AWS_DB_MAX_REPLICAS)
        new_db_cooldown = AWS_DB_SCALE_DELAY_STEPS
        db_scale_event = f"Replica {db_replicas}台 → {new_db_replicas}台 に追加"
        db_load_per_replica = min(users / (new_db_replicas * 4000) * 100, 100.0)

    # クエリ時間: レプリカ数で分散するため安定
    db_query_ms = 20 + (users / (new_db_replicas * 8000)) * 150

    return (
        {
            "cpu_per_instance": cpu_per_instance,
            "response_time": response_time,
            "current_users": users,
            "instances": new_instances,
            "scale_event": scale_event,
            "db_replicas": new_db_replicas,
            "db_query_ms": db_query_ms,
            "db_load_per_replica": db_load_per_replica,
            "db_scale_event": db_scale_event,
        },
        new_instances,
        new_cooldown,
        new_db_replicas,
        new_db_cooldown,
    )


if __name__ == "__main__":
    # 動作確認
    print("=== ramp_up ===")
    for s in [0, 5, 10, 15, 20, 25, 30]:
        print(f"  step={s}: {ramp_up(12000, s, 30):,}人")

    print("\n=== Streamlit Cloud ===")
    for u in [500, 1000, 2000, 3000, 5000]:
        state = compute_streamlit_state(u)
        print(f"  {u:,}人: CPU={state['cpu']:.0f}% RT={state['response_time']:.1f}s crashed={state['is_crashed']}")

    print("\n=== AWS / Azure ===")
    instances = 1
    cooldown = 0
    for u in [500, 1000, 3000, 6000, 12000]:
        state, instances, cooldown = compute_aws_state(u, instances, cooldown)
        print(f"  {u:,}人: {instances}台 CPU/台={state['cpu_per_instance']:.0f}% RT={state['response_time']:.2f}s")
