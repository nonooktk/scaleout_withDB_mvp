import time
import streamlit as st
import pandas as pd
from constants import (
    SLIDER_MIN, SLIDER_MAX, SLIDER_DEFAULT, SLIDER_STEP,
    SIMULATION_STEPS, SIMULATION_INTERVAL_SEC,
)
from components import render_streamlit_panel, render_aws_panel, render_chart
from simulation import ramp_up, compute_streamlit_state, compute_aws_state

st.set_page_config(page_title="AWS vs Streamlit Cloud", layout="wide")

st.title("大規模アクセス体験デモ")
st.caption("Streamlit Cloud と AWS / Azure — 大規模アクセス時の違いを体験しよう")

# --- コントロールエリア ---
target_users = st.slider(
    "同時アクセス数",
    min_value=SLIDER_MIN,
    max_value=SLIDER_MAX,
    value=SLIDER_DEFAULT,
    step=SLIDER_STEP,
    format="%d人",
)

col_btn1, col_btn2, _ = st.columns([1, 1, 6])
with col_btn1:
    start = st.button("アクセス開始", type="primary")
with col_btn2:
    reset = st.button("リセット")

st.divider()

# --- 左右パネル ---
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("Streamlit Cloud")
    st.caption("CPU: 2コア固定 / メモリ: 2.7GB固定 / スケールアウト不可")
    left_placeholder = st.empty()

with right_col:
    st.subheader("AWS / Azure")
    st.caption("ロードバランサー + オートスケーリング対応")
    right_placeholder = st.empty()

st.divider()

# --- グラフエリア ---
st.subheader("応答時間の推移（秒）")
st.caption("赤: Streamlit Cloud　　青: AWS / Azure")
chart_placeholder = st.empty()

# --- session_state 初期化 ---
if "running" not in st.session_state:
    st.session_state.running = False
if "chart_data" not in st.session_state:
    st.session_state.chart_data = pd.DataFrame(
        {"Streamlit Cloud": pd.Series(dtype=float), "AWS / Azure": pd.Series(dtype=float)}
    )
if "aws_instances" not in st.session_state:
    st.session_state.aws_instances = 1
if "scale_cooldown" not in st.session_state:
    st.session_state.scale_cooldown = 0
if "db_replicas" not in st.session_state:
    st.session_state.db_replicas = 1
if "db_scale_cooldown" not in st.session_state:
    st.session_state.db_scale_cooldown = 0

# --- ボタン処理 ---
if reset:
    st.session_state.running = False
    st.session_state.chart_data = pd.DataFrame(
        {"Streamlit Cloud": pd.Series(dtype=float), "AWS / Azure": pd.Series(dtype=float)}
    )
    st.session_state.aws_instances = 1
    st.session_state.scale_cooldown = 0
    st.session_state.db_replicas = 1
    st.session_state.db_scale_cooldown = 0
    st.rerun()

# --- 初期表示（未実行時）---
if not st.session_state.running and not start:
    with left_placeholder.container():
        st.info("「アクセス開始」を押してシミュレーションを開始してください")
    with right_placeholder.container():
        st.info("「アクセス開始」を押してシミュレーションを開始してください")
    render_chart(chart_placeholder, st.session_state.chart_data)

# --- アニメーションループ ---
if start or st.session_state.running:
    st.session_state.running = True
    aws_instances = st.session_state.aws_instances
    scale_cooldown = st.session_state.scale_cooldown
    db_replicas = st.session_state.db_replicas
    db_scale_cooldown = st.session_state.db_scale_cooldown
    chart_data = st.session_state.chart_data.copy()
    if chart_data.empty:
        chart_data = pd.DataFrame(
            {"Streamlit Cloud": pd.Series(dtype=float), "AWS / Azure": pd.Series(dtype=float)}
        )

    for step in range(SIMULATION_STEPS):
        current_users = ramp_up(target_users, step, SIMULATION_STEPS)

        # Streamlit Cloud の状態計算
        sc_state = compute_streamlit_state(current_users)

        # AWS / Azure の状態計算
        aws_state, aws_instances, scale_cooldown, db_replicas, db_scale_cooldown = compute_aws_state(
            current_users, aws_instances, scale_cooldown, db_replicas, db_scale_cooldown
        )

        # パネル描画
        render_streamlit_panel(left_placeholder, sc_state)
        render_aws_panel(right_placeholder, aws_state)

        # グラフデータ更新
        sc_rt = sc_state["response_time"] if not sc_state["is_crashed"] else None
        aws_rt = aws_state["response_time"]
        new_row = pd.DataFrame(
            [{"Streamlit Cloud": sc_rt, "AWS / Azure": aws_rt}]
        )
        chart_data = pd.concat([chart_data, new_row], ignore_index=True)
        render_chart(chart_placeholder, chart_data)

        time.sleep(SIMULATION_INTERVAL_SEC)

    # 完了後に状態を保存
    st.session_state.aws_instances = aws_instances
    st.session_state.scale_cooldown = scale_cooldown
    st.session_state.db_replicas = db_replicas
    st.session_state.db_scale_cooldown = db_scale_cooldown
    st.session_state.chart_data = chart_data
    st.session_state.running = False
