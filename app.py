import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import json

# --- 1. KẾT NỐI SUPABASE ---
try:
    # Dòng này phải thụt vào
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

# CSS tùy chỉnh cho giao diện sạch sẽ
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] { background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; }
    h1, h2, h3 { color: #2c3e50; }
    .success-text { color: #28a745; font-weight: bold; }
    .danger-text { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 3. MENU ĐIỀU HƯỚNG (SIDEBAR) ---
with st.sidebar:
    st.title("💸 Credit POS Manager")
    menu = st.radio("Menu chính", ["Giao dịch mới", "Quản lý Khách & Thẻ", "Kho Máy POS", "Báo cáo ngày"])
    st.divider()
    st.info("Phiên bản: 1.0.0 (MVP)")

# --- 4. CÁC HÀM HỖ TRỢ (HELPER FUNCTIONS) ---
def get_pos_list():
    return supabase.table("pos_terminals").select("*").eq("active", True).execute().data

def get_customers():
    return supabase.table("customers").select("*").execute().data

def get_cards_by_customer(customer_id):
    return supabase.table("credit_cards").select("*").eq("customer_id", customer_id).execute().data

# --- TRANG 1: GIAO DỊCH MỚI (MÀN HÌNH CHÍNH) ---
if menu == "Giao dịch mới":
    st.header("⚡ Tạo Giao Dịch Mới")
    
    # Lấy dữ liệu cần thiết
    customers = get_customers()
    pos_list = get_pos_list()
    
    if not customers:
        st.warning("Chưa có dữ liệu Khách hàng. Vui lòng sang tab 'Quản lý Khách & Thẻ' để thêm.")
        st.stop()
    if not pos_list:
        st.warning("Chưa có máy POS nào. Vui lòng sang tab 'Kho Máy POS' để thêm.")
        st.stop()

    with st.form("transaction_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Chọn khách hàng
            cust_options = {c['id']: f"{c['full_name']} - {c['phone']}" for c in customers}
            selected_cust_id = st.selectbox("1. Chọn Khách hàng", list(cust_options.keys()), format_func=lambda x: cust_options[x])
            
            # Chọn thẻ (Load động theo khách)
            # Lưu ý: Streamlit form không reload động tốt, nên ta lấy hết thẻ rồi lọc
            # Trong thực tế sẽ dùng st.rerun() nhưng ở bước 1 làm đơn giản trước
            cards = get_cards_by_customer(selected_cust_id)
            if cards:
                card_options = {c['id']: f"{c['bank_name']} - {c['card_type']} (...{c['last_4_digits']})" for c in cards}
                selected_card_id = st.selectbox("2. Chọn Thẻ", list(card_options.keys()), format_func=lambda x: card_options[x])
                
                # Tìm thông tin thẻ để lấy loại thẻ (Visa/Master)
                selected_card_info = next((c for c in cards if c['id'] == selected_card_id), None)
            else:
                st.error("Khách này chưa có thẻ nào!")
                selected_card_id = None
                selected_card_info = None

            amount = st.number_input("3. Số tiền giao dịch", min_value=0, step=1000000, format="%d")

        with col2:
            # Chọn POS
            pos_options = {p['id']: p['pos_name'] for p in pos_list}
            selected_pos_id = st.selectbox("4. Chọn Máy POS quẹt", list(pos_options.keys()), format_func=lambda x: pos_options[x])
            
            # Tìm thông tin POS để tính phí gốc
            selected_pos_info = next((p for p in pos_list if p['id'] == selected_pos_id), None)
            
            # Tính toán phí Gốc (Cost)
            pos_cost_percent = 0.0
            if selected_card_info and selected_pos_info:
                card_type = selected_card_info['card_type'].lower() # visa/master/jcb
                fee_config = selected_pos_info.get('fee_config', {})
                # Lấy phí từ config, nếu không có lấy mặc định 1.2
                pos_cost_percent = fee_config.get(card_type, 1.2)
                
            st.info(f"ℹ️ Phí gốc POS ({selected_pos_info['pos_name'] if selected_pos_info else ''}): **{pos_cost_percent}%**")

            # Nhập phí thu khách
            customer_fee_percent = st.number_input("5. Phí thu khách (%)", min_value=0.0, value=1.8, step=0.1)
            
            # Loại giao dịch
            trans_type = st.radio("Loại giao dịch", ["Rút tiền", "Đáo hạn"], horizontal=True)

        st.divider()
        
        # Tính toán Lợi nhuận Real-time
        if amount > 0:
            cust_fee_amt = amount * (customer_fee_percent / 100)
            pos_cost_amt = amount * (pos_cost_percent / 100)
            profit = cust_fee_amt - pos_cost_amt
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Thu khách", f"{cust_fee_amt:,.0f} đ")
            c2.metric("Trả POS", f"{pos_cost_amt:,.0f} đ")
            c3.metric("Lợi nhuận ròng", f"{profit:,.0f} đ", delta_color="normal")
        else:
            cust_fee_amt = 0; pos_cost_amt = 0; profit = 0

        note = st.text_input("Ghi chú")
        submitted = st.form_submit_button("✅ HOÀN TẤT GIAO DỊCH", use_container_width=True)

        if submitted and selected_card_id and amount > 0:
            # Ghi vào Database
            new_trans = {
                "card_id": selected_card_id,
                "pos_id": selected_pos_id,
                "type": trans_type,
                "amount": amount,
                "customer_fee_percent": customer_fee_percent,
                "customer_fee_amount": cust_fee_amt,
                "pos_cost_percent": pos_cost_percent,
                "pos_cost_amount": pos_cost_amt,
                "net_profit": profit,
                "note": note,
                "status": "Hoàn thành"
            }
            try:
                supabase.table("transactions").insert(new_trans).execute()
                st.success("Đã lưu giao dịch thành công!")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi lưu data: {e}")

# --- TRANG 2: QUẢN LÝ KHÁCH HÀNG & THẺ ---
elif menu == "Quản lý Khách & Thẻ":
    tab1, tab2 = st.tabs(["👥 Thêm Khách Hàng", "💳 Thêm Thẻ Tín Dụng"])
    
    with tab1:
        with st.form("add_customer"):
            st.subheader("Thêm khách hàng mới")
            new_name = st.text_input("Họ và Tên")
            new_phone = st.text_input("Số điện thoại (Bắt buộc)")
            new_cccd = st.text_input("Số CCCD")
            new_note = st.text_input("Ghi chú khách hàng")
            
            if st.form_submit_button("Lưu Khách Hàng"):
                if new_name and new_phone:
                    try:
                        supabase.table("customers").insert({
                            "full_name": new_name, "phone": new_phone, 
                            "cccd_number": new_cccd, "note": new_note
                        }).execute()
                        st.success(f"Đã thêm khách {new_name}")
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                else:
                    st.warning("Vui lòng nhập Tên và SĐT")
    
    with tab2:
        customers = get_customers()
        cust_map = {c['id']: c['full_name'] for c in customers}
        
        with st.form("add_card"):
            st.subheader("Thêm thẻ cho khách")
            c_id = st.selectbox("Chọn Khách", list(cust_map.keys()), format_func=lambda x: cust_map[x])
            bank = st.selectbox("Ngân hàng", ["Techcombank", "VPBank", "VIB", "TPBank", "Sacombank", "MBBank", "Khác"])
            c_type = st.selectbox("Loại thẻ", ["VISA", "MASTER", "JCB", "NAPAS"])
            last_4 = st.text_input("4 số cuối thẻ", max_chars=4)
            limit = st.number_input("Hạn mức thẻ", step=1000000)
            due_day = st.number_input("Ngày đáo hạn (VD: Ngày 5)", min_value=1, max_value=31)
            
            if st.form_submit_button("Lưu Thẻ"):
                try:
                    supabase.table("credit_cards").insert({
                        "customer_id": c_id, "bank_name": bank, "card_type": c_type,
                        "last_4_digits": last_4, "credit_limit": limit, "due_date": due_day
                    }).execute()
                    st.success("Đã thêm thẻ thành công")
                except Exception as e:
                    st.error(f"Lỗi: {e}")
    
    # Hiển thị danh sách khách hiện tại
    st.divider()
    st.subheader("Danh sách khách hàng hiện có")
    all_cust = pd.DataFrame(customers)
    if not all_cust.empty:
        st.dataframe(all_cust[['full_name', 'phone', 'note', 'created_at']], use_container_width=True)

# --- TRANG 3: KHO MÁY POS ---
elif menu == "Kho Máy POS":
    st.subheader("📦 Quản lý nguồn POS")
    
    with st.expander("➕ Thêm Máy POS Mới"):
        with st.form("add_pos"):
            p_name = st.text_input("Tên máy (VD: Máy Bún chả)")
            p_owner = st.text_input("Chủ máy (Nguồn thuê)")
            
            c1, c2, c3 = st.columns(3)
            fee_visa = c1.number_input("Phí VISA (%)", value=1.2, step=0.1)
            fee_master = c2.number_input("Phí MASTER (%)", value=1.2, step=0.1)
            fee_jcb = c3.number_input("Phí JCB (%)", value=1.4, step=0.1)
            
            if st.form_submit_button("Lưu Máy POS"):
                config = {"visa": fee_visa, "master": fee_master, "jcb": fee_jcb, "napas": 0.8}
                supabase.table("pos_terminals").insert({
                    "pos_name": p_name, "owner_name": p_owner, "fee_config": config
                }).execute()
                st.success("Đã thêm máy POS mới")
                st.rerun()

    # Hiển thị danh sách POS
    pos_data = get_pos_list()
    if pos_data:
        st.dataframe(pos_data)
    else:
        st.info("Chưa có máy POS nào.")

# --- TRANG 4: BÁO CÁO NGÀY (CƠ BẢN) ---
elif menu == "Báo cáo ngày":
    st.subheader("📊 Báo cáo giao dịch hôm nay")
    
    # Lấy giao dịch trong ngày
    today = datetime.date.today().isoformat()
    # Query: created_at >= hôm nay
    # Lưu ý: Demo lấy 100 gd gần nhất cho nhanh
    response = supabase.table("transactions").select("*").order("created_at", desc=True).limit(50).execute()
    trans = response.data
    
    if trans:
        df = pd.DataFrame(trans)
        
        # KPI Tổng quan
        total_rev = df['amount'].sum()
        total_profit = df['net_profit'].sum()
        count = len(df)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Số giao dịch", count)
        m2.metric("Tổng doanh số", f"{total_rev:,.0f} đ")
        m3.metric("Lợi nhuận ròng", f"{total_profit:,.0f} đ")
        
        st.dataframe(df[['created_at', 'type', 'amount', 'net_profit', 'note']], use_container_width=True)
    else:
        st.info("Hôm nay chưa có giao dịch nào.")
