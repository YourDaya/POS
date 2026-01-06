import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import json
import time

# --- 1. KẾT NỐI SUPABASE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Chưa cấu hình Secrets!")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# --- 2. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Credit POS Pro", page_icon="💳", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] { background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; }
    h1, h2, h3 { color: #2c3e50; }
    .success-text { color: #28a745; font-weight: bold; }
    /* Chỉnh sửa bảng data editor cho dễ nhìn */
    div[data-testid="stDataEditor"] { border: 1px solid #ddd; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- 3. MENU ĐIỀU HƯỚNG ---
with st.sidebar:
    st.title("💸 Credit POS Manager")
    menu = st.radio("Menu chính", ["Giao dịch mới", "Quản lý Khách & Thẻ", "Kho Máy POS", "Báo cáo ngày"])
    st.divider()
    st.caption("Phiên bản: 1.1.0 (Update Bank & POS)")

# --- 4. HÀM HỖ TRỢ ---
def get_pos_list(active_only=True):
    query = supabase.table("pos_terminals").select("*").order("created_at")
    if active_only:
        query = query.eq("active", True)
    return query.execute().data

def get_customers():
    return supabase.table("customers").select("*").order("created_at", desc=True).execute().data

def get_cards_by_customer(customer_id):
    return supabase.table("credit_cards").select("*").eq("customer_id", customer_id).execute().data

# Hàm lấy danh sách ngân hàng duy nhất đã có trong DB
def get_existing_banks():
    # Lấy tất cả tên ngân hàng đã lưu
    data = supabase.table("credit_cards").select("bank_name").execute().data
    if data:
        # Lọc trùng lặp
        banks = sorted(list(set([item['bank_name'] for item in data])))
        return banks
    return []

# --- TRANG 1: GIAO DỊCH MỚI ---
if menu == "Giao dịch mới":
    st.header("⚡ Tạo Giao Dịch Mới")
    
    customers = get_customers()
    # Chỉ lấy máy POS đang hoạt động (active=True)
    pos_list = get_pos_list(active_only=True)
    
    if not customers:
        st.warning("Chưa có khách hàng. Vui lòng thêm trước.")
        st.stop()
    if not pos_list:
        st.warning("Không có máy POS nào đang hoạt động. Vui lòng kiểm tra Kho Máy POS.")
        st.stop()

    with st.form("transaction_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            cust_options = {c['id']: f"{c['full_name']} - {c['phone']}" for c in customers}
            selected_cust_id = st.selectbox("1. Chọn Khách hàng", list(cust_options.keys()), format_func=lambda x: cust_options[x])
            
            cards = get_cards_by_customer(selected_cust_id)
            if cards:
                card_options = {c['id']: f"{c['bank_name']} - {c['card_type']} (...{c['last_4_digits']})" for c in cards}
                selected_card_id = st.selectbox("2. Chọn Thẻ", list(card_options.keys()), format_func=lambda x: card_options[x])
                selected_card_info = next((c for c in cards if c['id'] == selected_card_id), None)
            else:
                st.error("Khách này chưa có thẻ nào!")
                selected_card_id = None
                selected_card_info = None

            amount = st.number_input("3. Số tiền giao dịch", min_value=0, step=1000000, format="%d")

        with col2:
            # Dropdown chỉ hiện POS đang Active
            pos_options = {p['id']: p['pos_name'] for p in pos_list}
            selected_pos_id = st.selectbox("4. Chọn Máy POS", list(pos_options.keys()), format_func=lambda x: pos_options[x])
            selected_pos_info = next((p for p in pos_list if p['id'] == selected_pos_id), None)
            
            pos_cost_percent = 0.0
            if selected_card_info and selected_pos_info:
                card_type = selected_card_info['card_type'].lower()
                fee_config = selected_pos_info.get('fee_config', {})
                pos_cost_percent = fee_config.get(card_type, 1.2)
                
            st.info(f"ℹ️ Phí gốc POS: **{pos_cost_percent}%**")
            customer_fee_percent = st.number_input("5. Phí thu khách (%)", min_value=0.0, value=1.8, step=0.1)
            trans_type = st.radio("Loại giao dịch", ["Rút tiền", "Đáo hạn"], horizontal=True)

        st.divider()
        
        if amount > 0:
            cust_fee_amt = amount * (customer_fee_percent / 100)
            pos_cost_amt = amount * (pos_cost_percent / 100)
            profit = cust_fee_amt - pos_cost_amt
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Thu khách", f"{cust_fee_amt:,.0f}")
            c2.metric("Trả POS", f"{pos_cost_amt:,.0f}")
            c3.metric("Lợi nhuận", f"{profit:,.0f}", delta_color="normal")

        submitted = st.form_submit_button("✅ HOÀN TẤT", use_container_width=True)

        if submitted and selected_card_id and amount > 0:
            new_trans = {
                "card_id": selected_card_id, "pos_id": selected_pos_id,
                "type": trans_type, "amount": amount,
                "customer_fee_percent": customer_fee_percent, "customer_fee_amount": cust_fee_amt,
                "pos_cost_percent": pos_cost_percent, "pos_cost_amount": pos_cost_amt,
                "net_profit": profit, "status": "Hoàn thành"
            }
            try:
                supabase.table("transactions").insert(new_trans).execute()
                st.toast("Lưu thành công!", icon="🎉")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")

# --- TRANG 2: QUẢN LÝ KHÁCH & THẺ (CẬP NHẬT NGÂN HÀNG) ---
elif menu == "Quản lý Khách & Thẻ":
    tab1, tab2 = st.tabs(["👥 Thêm Khách Hàng", "💳 Thêm Thẻ Tín Dụng"])
    
    with tab1:
        with st.form("add_customer"):
            st.subheader("Thêm khách hàng")
            new_name = st.text_input("Họ và Tên")
            new_phone = st.text_input("Số điện thoại")
            new_cccd = st.text_input("CCCD")
            if st.form_submit_button("Lưu"):
                if new_name and new_phone:
                    supabase.table("customers").insert({"full_name": new_name, "phone": new_phone, "cccd_number": new_cccd}).execute()
                    st.success("Đã thêm khách!")
                else:
                    st.warning("Cần nhập Tên và SĐT")
    
    with tab2:
        customers = get_customers()
        cust_map = {c['id']: c['full_name'] for c in customers}
        
        # --- LOGIC CHỌN NGÂN HÀNG LINH HOẠT ---
        st.subheader("Thêm thẻ mới")
        with st.form("add_card"):
            c_id = st.selectbox("Khách hàng", list(cust_map.keys()), format_func=lambda x: cust_map[x])
            
            # 1. Lấy danh sách ngân hàng đã có trong DB
            existing_banks = get_existing_banks()
            # 2. Danh sách mặc định phổ biến
            default_banks = ["Techcombank", "VPBank", "VIB", "TPBank", "Sacombank", "MBBank", "ACB", "Vietcombank"]
            # 3. Gộp lại và loại bỏ trùng
            all_bank_options = sorted(list(set(default_banks + existing_banks)))
            # 4. Thêm tùy chọn nhập mới
            all_bank_options.append("➕ Nhập ngân hàng khác...")
            
            selected_bank_option = st.selectbox("Ngân hàng", all_bank_options)
            
            # Nếu chọn nhập khác thì hiện ô text
            final_bank_name = selected_bank_option
            if selected_bank_option == "➕ Nhập ngân hàng khác...":
                custom_bank = st.text_input("Nhập tên ngân hàng (Ví dụ: ABB, Shinhan...)")
                if custom_bank:
                    final_bank_name = custom_bank.strip()
                else:
                    final_bank_name = "" # Để chặn submit nếu để trống
            
            c_type = st.selectbox("Loại thẻ", ["VISA", "MASTER", "JCB", "NAPAS"])
            last_4 = st.text_input("4 số cuối")
            limit = st.number_input("Hạn mức", step=1000000)
            due_day = st.number_input("Ngày đáo (1-31)", min_value=1, max_value=31)
            
            if st.form_submit_button("Lưu Thẻ"):
                if final_bank_name and final_bank_name != "➕ Nhập ngân hàng khác...":
                    supabase.table("credit_cards").insert({
                        "customer_id": c_id, "bank_name": final_bank_name,
                        "card_type": c_type, "last_4_digits": last_4,
                        "credit_limit": limit, "due_date": due_day
                    }).execute()
                    st.success(f"Đã thêm thẻ {final_bank_name}!")
                    time.sleep(1)
                    st.rerun() # Reload để cập nhật danh sách ngân hàng
                else:
                    st.error("Vui lòng nhập tên ngân hàng!")

# --- TRANG 3: KHO MÁY POS (CẬP NHẬT TRẠNG THÁI) ---
elif menu == "Kho Máy POS":
    st.subheader("📦 Quản lý & Cấu hình POS")
    
    # 1. Form thêm mới (Giữ nguyên)
    with st.expander("➕ Thêm Máy POS Mới"):
        with st.form("add_pos"):
            p_name = st.text_input("Tên máy")
            p_owner = st.text_input("Chủ máy")
            c1, c2, c3 = st.columns(3)
            f_v = c1.number_input("Phí VISA", 1.2)
            f_m = c2.number_input("Phí MASTER", 1.2)
            f_j = c3.number_input("Phí JCB", 1.4)
            if st.form_submit_button("Lưu"):
                cfg = {"visa": f_v, "master": f_m, "jcb": f_j, "napas": 0.8}
                supabase.table("pos_terminals").insert({"pos_name": p_name, "owner_name": p_owner, "fee_config": cfg}).execute()
                st.success("Đã thêm!")
                st.rerun()
    
    st.divider()
    
    # 2. Bảng Danh sách POS (Có thể chỉnh sửa Active/Inactive)
    st.write("Danh sách máy hiện có (Bỏ tick 'active' để ngừng sử dụng):")
    
    # Lấy toàn bộ máy (cả cũ và mới)
    all_pos = get_pos_list(active_only=False)
    
    if all_pos:
        # Chuyển sang DataFrame để hiển thị đẹp
        df_pos = pd.DataFrame(all_pos)
        
        # Chỉ lấy các cột cần thiết để edit
        df_editor = df_pos[['id', 'active', 'pos_name', 'owner_name', 'created_at']]
        
        # Hiển thị bảng Edit được
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "active": st.column_config.CheckboxColumn(
                    "Đang hoạt động?",
                    help="Bỏ tick để ẩn máy này khỏi màn hình giao dịch",
                    default=True,
                ),
                "id": st.column_config.TextColumn("ID", disabled=True),
                "pos_name": "Tên máy",
                "owner_name": "Chủ sở hữu",
                "created_at": st.column_config.DatetimeColumn("Ngày tạo", disabled=True, format="D/M/Y"),
            },
            disabled=["id", "created_at"], # Không cho sửa ID và ngày tạo
            hide_index=True,
            use_container_width=True,
            key="pos_editor"
        )
        
        # Nút Lưu thay đổi
        if st.button("💾 Cập nhật trạng thái POS"):
            # Logic: So sánh data cũ và mới để update (hoặc update tất cả active status)
            # Để đơn giản, ta lặp qua edited_df và update status lên server
            try:
                # Chuyển đổi về list dict
                updates = edited_df.to_dict('records')
                
                # Update từng dòng (Supabase chưa support bulk update dễ dàng qua thư viện này nên ta loop)
                # Đây là cách an toàn cho MVP
                progress_bar = st.progress(0)
                for i, row in enumerate(updates):
                    supabase.table("pos_terminals").update({"active": row['active'], "pos_name": row['pos_name'], "owner_name": row['owner_name']}).eq("id", row['id']).execute()
                    progress_bar.progress((i + 1) / len(updates))
                
                st.success("Đã cập nhật trạng thái các máy POS!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi cập nhật: {e}")

# --- TRANG 4: BÁO CÁO ---
elif menu == "Báo cáo ngày":
    st.subheader("📊 Giao dịch gần đây")
    trans = supabase.table("transactions").select("*").order("created_at", desc=True).limit(50).execute().data
    if trans:
        st.dataframe(trans)
    else:
        st.info("Chưa có giao dịch.")
