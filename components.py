import streamlit as st
import pandas as pd


def render_streamlit_panel(placeholder, state: dict) -> None:
    """左カラム: Streamlit Cloud の状態を描画"""
    with placeholder.container():
        if state["is_crashed"]:
            st.markdown(
                """
                <div style="background:#ff4b4b;color:white;padding:20px;border-radius:8px;
                            text-align:center;animation:blink 0.5s step-start infinite;">
                    <h2 style="margin:0;">⚡ SYSTEM CRASH ⚡</h2>
                    <p style="font-size:1.2em;margin:8px 0;">503 Service Unavailable</p>
                    <p style="margin:0;">大量アクセスによりサーバーが停止しました</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.metric("CPU使用率", "100%")
            st.progress(1.0)
            st.metric("応答時間", "タイムアウト")
            st.metric("現在のアクセス数", f"{state['current_users']:,}人")
            st.error("スケールアウト不可のため復旧できません")
        else:
            cpu = state["cpu"]
            mem = state["memory"]
            rt = state["response_time"]

            col1, col2 = st.columns(2)
            with col1:
                st.metric("CPU使用率", f"{cpu:.0f}%")
                st.progress(min(cpu / 100, 1.0))
            with col2:
                st.metric("メモリ使用率", f"{mem:.0f}%")
                st.progress(min(mem / 100, 1.0))

            st.metric("応答時間", f"{rt:.1f}秒")
            st.metric("現在のアクセス数", f"{state['current_users']:,}人")

            if cpu >= 90:
                st.error("CPU使用率が危険域！もうすぐクラッシュします")
            elif cpu >= 70:
                st.warning("CPU使用率が高くなっています（スケールアウト不可）")
            else:
                st.success("正常稼働中")

        # --- DB層 ---
        st.divider()
        st.markdown("**🗄️ データベース（単一インスタンス）**")
        db_q = state["db_query_ms"]
        db_conn = state["db_connections"]
        conn_ratio = db_conn / 500

        if state["is_crashed"]:
            st.markdown(
                """
                <div style="background:#ff4b4b;color:white;padding:10px 14px;
                            border-radius:6px;text-align:center;">
                    <strong>💥 DB接続エラー / タイムアウト</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif state["db_overloaded"]:
            st.metric("クエリ時間", f"{db_q:.0f}ms ⬆")
            st.progress(min(conn_ratio, 1.0))
            st.caption(f"接続数: {db_conn} / 500")
            st.warning("DB過負荷：クエリ遅延・接続枯渇が発生しています")
        else:
            st.metric("クエリ時間", f"{db_q:.0f}ms")
            st.progress(min(conn_ratio, 1.0))
            st.caption(f"接続数: {db_conn} / 500")


def render_aws_panel(placeholder, state: dict) -> None:
    """右カラム: AWS / Azure の状態を描画"""
    with placeholder.container():
        # ロードバランサー
        st.markdown(
            """
            <div style="background:#fff3cd;border:2px solid #ffc107;padding:10px 16px;
                        border-radius:8px;text-align:center;margin-bottom:12px;">
                🔀 <strong>ロードバランサー</strong>　リクエストを自動で振り分け
            </div>
            """,
            unsafe_allow_html=True,
        )

        # スケールアウトイベント通知
        if state.get("scale_event"):
            st.toast(f"🚀 オートスケール: {state['scale_event']}", icon="🚀")

        # EC2インスタンス表示（最大4台まで横並び、超過分は別表示）
        instances = state["instances"]
        display_count = min(instances, 4)
        cols = st.columns(display_count)
        cpu_i = state["cpu_per_instance"]
        color = "#d4edda" if cpu_i < 70 else "#fff3cd"

        for i, col in enumerate(cols):
            with col:
                st.markdown(
                    f"""
                    <div style="background:{color};border:1px solid #aaa;padding:10px 6px;
                                border-radius:6px;text-align:center;font-size:0.85em;">
                        <strong>EC2-{i+1}</strong><br>
                        CPU: {cpu_i:.0f}%
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if instances > 4:
            st.caption(f"+ {instances - 4}台 稼働中（合計 {instances}台）")

        st.metric("応答時間", f"{state['response_time']:.1f}秒")
        st.metric("現在のアクセス数", f"{state['current_users']:,}人")
        st.metric("稼働インスタンス数", f"{instances}台")
        st.success(f"安定稼働中（{instances}台でロードバランシング）")

        # --- DB層 ---
        st.divider()
        st.markdown("**🗄️ RDS / Azure SQL（リードレプリカ構成）**")

        if state.get("db_scale_event"):
            st.toast(f"🗄️ DBスケール: {state['db_scale_event']}", icon="🗄️")

        db_replicas = state["db_replicas"]
        db_q = state["db_query_ms"]
        db_load = state["db_load_per_replica"]

        # Primary + Replicaのボックス表示（最大Primary+3Replica = 4列）
        display_db = min(db_replicas + 1, 4)  # Primary 1台 + Replica分
        db_cols = st.columns(display_db)
        with db_cols[0]:
            st.markdown(
                """
                <div style="background:#cce5ff;border:1px solid #6baed6;padding:8px 4px;
                            border-radius:6px;text-align:center;font-size:0.8em;">
                    <strong>📝 Primary</strong><br>書き込み
                </div>
                """,
                unsafe_allow_html=True,
            )
        replica_color = "#d4edda" if db_load < 70 else "#fff3cd"
        for i, col in enumerate(db_cols[1:], start=1):
            with col:
                st.markdown(
                    f"""
                    <div style="background:{replica_color};border:1px solid #aaa;padding:8px 4px;
                                border-radius:6px;text-align:center;font-size:0.8em;">
                        <strong>📖 Replica-{i}</strong><br>読み取り
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if db_replicas > 3:
            st.caption(f"+ {db_replicas - 3}台 追加中（合計 {db_replicas}台のReplica）")

        st.metric("クエリ時間", f"{db_q:.0f}ms")
        st.caption(f"Replica負荷: {db_load:.0f}%　読み取りを自動分散中")
        st.success(f"DB安定（Primary + Replica {db_replicas}台で分散）")


def render_chart(placeholder, chart_data: pd.DataFrame) -> None:
    """応答時間の推移グラフを描画"""
    with placeholder.container():
        if chart_data.empty or chart_data.dropna(how="all").empty:
            return
        st.line_chart(
            chart_data,
            color=["#ff4b4b", "#1f77b4"],
        )
