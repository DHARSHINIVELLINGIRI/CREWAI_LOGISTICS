"""
MongoDB Explorer — Built-in database browser for the Eshipz Admin.
Provides a full CRUD interface to MongoDB directly inside the Streamlit app.
Call render_mongo_explorer(db) from app.py.
"""

import streamlit as st
import pandas as pd
import json
import datetime
from bson import ObjectId

# ── Helper: serialize BSON types for display ──────────────────────────────────
def _bson_serialize(obj):
    """Recursively convert BSON/datetime objects to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _bson_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_bson_serialize(i) for i in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def _doc_to_dict(doc) -> dict:
    return _bson_serialize(dict(doc))


def _flat_doc(doc: dict) -> dict:
    """Flatten nested dict one level for DataFrame display."""
    flat = {}
    for k, v in doc.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v
    return flat


# ── Main renderer ─────────────────────────────────────────────────────────────
def render_mongo_explorer(db=None):
    st.markdown("""
    <style>
    .mongo-header {
        background: linear-gradient(135deg, #1a1f2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
        border: 1px solid #225;
    }
    .mongo-badge {
        display: inline-block;
        background: #00ED64;
        color: #001e2b;
        border-radius: 6px;
        padding: 2px 10px;
        font-weight: 700;
        font-size: 0.78rem;
        margin-right: 8px;
    }
    .mongo-title {
        font-size: 1.5rem;
        font-weight: 800;
        color: #E8ECF3;
        margin: 0;
    }
    .mongo-sub {
        color: #64748B;
        font-size: 0.85rem;
        margin-top: 4px;
    }
    .collection-card {
        background: #1E2330;
        border: 1px solid #2D3348;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: all 0.2s;
    }
    .collection-card:hover {
        border-color: #00ED64;
        background: #1a2a1e;
    }
    .stat-pill {
        background: #00ED6420;
        color: #00ED64;
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .doc-card {
        background: #1a1f2e;
        border: 1px solid #2a2f42;
        border-radius: 8px;
        padding: 12px;
        margin: 6px 0;
        font-family: 'Courier New', monospace;
        font-size: 0.8rem;
    }
    .section-divider {
        border: none;
        border-top: 1px solid #2D3348;
        margin: 16px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="mongo-header">
        <p class="mongo-title">
            <span class="mongo-badge">MONGO</span>Database Explorer
        </p>
        <p class="mongo-sub">🔒 Admin-only · Browse, search, insert, and delete documents in real-time</p>
    </div>
    """, unsafe_allow_html=True)

    # ── DB offline check ───────────────────────────────────────────────────────
    if db is None:
        st.error("🔴 **MongoDB is offline.** Cannot connect to the database. Check your `MONGODB_URI` in `.env`.")
        with st.expander("🔧 Troubleshooting Tips"):
            st.markdown("""
            1. Verify `MONGODB_URI` in your `.env` file
            2. Check your internet connection (MongoDB Atlas requires internet)
            3. Ensure your IP is whitelisted in MongoDB Atlas → Network Access
            4. Check the Cluster is running in [MongoDB Atlas](https://cloud.mongodb.com)
            """)
        return

    # ── Fetch collections ──────────────────────────────────────────────────────
    try:
        collection_names = db.list_collection_names()
    except Exception as e:
        st.error(f"❌ Could not list collections: {e}")
        return

    if not collection_names:
        st.warning("⚠️ No collections found in the database.")
        collection_names = []

    # ── Sidebar-like left panel + main area ──────────────────────────────────
    col_left, col_main = st.columns([1, 3], gap="medium")

    with col_left:
        st.markdown("### 📚 Collections")

        # DB stats header
        try:
            db_stats = db.command("dbStats")
            total_docs = sum(db[c].count_documents({}) for c in collection_names)
            mem_mb = round(db_stats.get("dataSize", 0) / (1024 * 1024), 2)
            s1, s2 = st.columns(2)
            s1.metric("Collections", len(collection_names))
            s2.metric("Total Docs", total_docs)
            st.caption(f"💾 Data size: ~{mem_mb} MB")
        except Exception:
            pass

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Collection list as selectable buttons
        selected_collection = st.session_state.get("mongo_selected_coll", collection_names[0] if collection_names else None)

        for cname in collection_names:
            try:
                count = db[cname].count_documents({})
            except Exception:
                count = "?"
            is_selected = (cname == selected_collection)
            btn_style = "primary" if is_selected else "secondary"
            if st.button(
                f"{'▶ ' if is_selected else ''}{cname}  ({count} docs)",
                key=f"coll_btn_{cname}",
                use_container_width=True,
                type=btn_style
            ):
                st.session_state["mongo_selected_coll"] = cname
                st.session_state["mongo_page"] = 0
                st.rerun()

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # ── Create new collection ──────────────────────────────────────────────
        with st.expander("➕ New Collection"):
            new_coll_name = st.text_input("Collection name", key="new_coll_name")
            if st.button("Create", key="create_coll_btn", use_container_width=True):
                if new_coll_name.strip():
                    try:
                        db.create_collection(new_coll_name.strip())
                        st.success(f"✅ Created `{new_coll_name}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Enter a collection name.")

        # ── Drop collection ────────────────────────────────────────────────────
        with st.expander("🗑️ Drop Collection", expanded=False):
            st.warning("⚠️ This permanently deletes the collection and ALL its data!")
            drop_name = st.selectbox("Select collection to drop", collection_names, key="drop_coll_name")
            confirm_drop = st.text_input("Type the collection name to confirm", key="drop_confirm_input")
            if st.button("🗑️ Drop Collection", key="drop_coll_btn", type="primary", use_container_width=True):
                if confirm_drop == drop_name:
                    try:
                        db.drop_collection(drop_name)
                        if st.session_state.get("mongo_selected_coll") == drop_name:
                            st.session_state["mongo_selected_coll"] = None
                        st.success(f"✅ Dropped `{drop_name}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("Collection name doesn't match. Aborting.")

    # ── Main panel ─────────────────────────────────────────────────────────────
    with col_main:
        if not selected_collection or selected_collection not in collection_names:
            if collection_names:
                selected_collection = collection_names[0]
                st.session_state["mongo_selected_coll"] = selected_collection
            else:
                st.info("No collections available. Create one from the left panel.")
                return

        coll = db[selected_collection]

        # ── Collection header ──────────────────────────────────────────────────
        try:
            coll_count = coll.count_documents({})
            coll_stats = db.command("collStats", selected_collection)
            avg_doc = round(coll_stats.get("avgObjSize", 0), 0)
        except Exception:
            coll_count = "?"
            avg_doc = "?"

        header_col1, header_col2, header_col3, header_col4 = st.columns(4)
        header_col1.metric("📄 Collection", selected_collection)
        header_col2.metric("📊 Total Docs", coll_count)
        header_col3.metric("📦 Avg Doc Size", f"{avg_doc} B")
        header_col4.metric("🏷️ Status", "✅ Connected")

        st.markdown("---")

        # ── Main Tabs ─────────────────────────────────────────────────────────
        tab_browse, tab_query, tab_insert, tab_delete, tab_stats = st.tabs([
            "🔍 Browse", "🔎 Query", "➕ Insert", "🗑️ Delete", "📈 Stats"
        ])

        # ══════════════════════════════════════════════════════════════════════
        # TAB 1: BROWSE
        # ══════════════════════════════════════════════════════════════════════
        with tab_browse:
            st.subheader(f"📄 Documents in `{selected_collection}`")

            # Controls row
            b_col1, b_col2, b_col3 = st.columns([2, 1, 1])
            with b_col1:
                search_field = st.text_input(
                    "🔍 Quick search (field=value)",
                    placeholder='e.g. status=Booked  or  user_name=John',
                    key="browse_search"
                )
            with b_col2:
                page_size = st.selectbox("Docs per page", [10, 25, 50, 100], key="browse_page_size")
            with b_col3:
                view_mode = st.radio("View as", ["Table", "JSON"], horizontal=True, key="browse_view_mode")

            # Sort options
            try:
                sample_doc = coll.find_one()
                all_fields = list(sample_doc.keys()) if sample_doc else ["_id"]
            except Exception:
                all_fields = ["_id"]

            sc1, sc2 = st.columns(2)
            with sc1:
                sort_field = st.selectbox("Sort by", all_fields, key="browse_sort_field")
            with sc2:
                sort_dir = st.radio("Order", ["Descending", "Ascending"], horizontal=True, key="browse_sort_dir")

            sort_val = -1 if sort_dir == "Descending" else 1

            # Build filter
            browse_filter = {}
            if search_field:
                parts = search_field.split("=", 1)
                if len(parts) == 2:
                    field_name = parts[0].strip()
                    field_val  = parts[1].strip()
                    # Try numeric
                    try:
                        field_val = float(field_val) if "." in field_val else int(field_val)
                    except ValueError:
                        pass
                    browse_filter = {field_name: field_val}

            # Pagination
            page_num = st.session_state.get("mongo_page", 0)
            skip_n   = page_num * page_size

            try:
                total_filtered = coll.count_documents(browse_filter)
                docs = list(
                    coll.find(browse_filter)
                    .sort(sort_field, sort_val)
                    .skip(skip_n)
                    .limit(page_size)
                )
            except Exception as e:
                st.error(f"Query error: {e}")
                docs = []
                total_filtered = 0

            # Pagination controls
            total_pages = max(1, -(-total_filtered // page_size))  # ceil division
            pg_col1, pg_col2, pg_col3 = st.columns([1, 3, 1])
            with pg_col1:
                if st.button("⬅ Prev", key="prev_page_btn", disabled=(page_num == 0)):
                    st.session_state["mongo_page"] = max(0, page_num - 1)
                    st.rerun()
            with pg_col2:
                st.markdown(
                    f"<div style='text-align:center;color:#64748B;padding-top:8px;'>"
                    f"Page <b style='color:#E2E8F0'>{page_num + 1}</b> of {total_pages} "
                    f"· Showing {len(docs)} of <b style='color:#00ED64'>{total_filtered}</b> documents"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with pg_col3:
                if st.button("Next ➡", key="next_page_btn", disabled=(page_num >= total_pages - 1)):
                    st.session_state["mongo_page"] = min(total_pages - 1, page_num + 1)
                    st.rerun()

            st.markdown("")

            if not docs:
                st.info("📭 No documents found with the current filter.")
            elif view_mode == "Table":
                # Flatten all docs to DataFrame
                flat_docs = [_flat_doc(_doc_to_dict(d)) for d in docs]
                df = pd.DataFrame(flat_docs)
                # Limit columns for readability
                if len(df.columns) > 15:
                    df = df.iloc[:, :15]
                    st.caption("📌 Showing first 15 fields. Use JSON view for all fields.")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                # JSON view with nice cards
                for i, doc in enumerate(docs):
                    serial_doc = _doc_to_dict(doc)
                    oid = serial_doc.get("_id", f"doc_{i}")
                    with st.expander(f"📄 `{oid}`", expanded=(i < 3)):
                        st.json(serial_doc)

        # ══════════════════════════════════════════════════════════════════════
        # TAB 2: QUERY
        # ══════════════════════════════════════════════════════════════════════
        with tab_query:
            st.subheader("🔎 Advanced Query")
            st.caption("Write MongoDB-style JSON filter queries")

            q_col1, q_col2 = st.columns(2)
            with q_col1:
                query_str = st.text_area(
                    "Filter (JSON)",
                    value='{}',
                    height=120,
                    key="adv_query_str",
                    help='Example: {"status": "Booked"} or {"details.source": "Delhi"}'
                )
            with q_col2:
                projection_str = st.text_area(
                    "Projection (JSON) — optional",
                    value="{}",
                    height=120,
                    key="adv_projection_str",
                    help='Example: {"tracking_id": 1, "status": 1, "_id": 0}'
                )

            q_r1, q_r2, q_r3 = st.columns([2, 1, 1])
            with q_r1:
                query_limit = st.slider("Max results", 1, 500, 50, key="query_limit")
            with q_r2:
                query_sort_field = st.text_input("Sort field", value="_id", key="query_sort_field")
            with q_r3:
                query_sort_dir = st.radio("Sort", ["-1 (desc)", "1 (asc)"], key="query_sort_dir")
                query_sort_val = -1 if "-1" in query_sort_dir else 1

            run_btn = st.button("▶ Run Query", key="run_query_btn", type="primary", use_container_width=True)

            if run_btn:
                try:
                    filter_obj = json.loads(query_str)
                    proj_obj   = json.loads(projection_str) if projection_str.strip() != "{}" else None

                    find_kwargs = {}
                    if proj_obj:
                        find_kwargs["projection"] = proj_obj

                    results = list(
                        coll.find(filter_obj, **find_kwargs)
                        .sort(query_sort_field, query_sort_val)
                        .limit(query_limit)
                    )
                    st.session_state["mongo_query_results"] = results
                    st.success(f"✅ Found **{len(results)}** document(s)")
                except json.JSONDecodeError as je:
                    st.error(f"❌ Invalid JSON: {je}")
                except Exception as e:
                    st.error(f"❌ Query failed: {e}")

            # Show results
            results = st.session_state.get("mongo_query_results", [])
            if results:
                st.markdown("---")
                q_view = st.radio("View results as", ["Table", "JSON"], horizontal=True, key="query_view_mode")
                if q_view == "Table":
                    flat_results = [_flat_doc(_doc_to_dict(d)) for d in results]
                    df_q = pd.DataFrame(flat_results)
                    st.dataframe(df_q, use_container_width=True, hide_index=True)

                    # CSV download
                    csv = df_q.to_csv(index=False)
                    st.download_button(
                        "⬇ Download CSV",
                        data=csv,
                        file_name=f"{selected_collection}_query_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key="download_csv_btn"
                    )
                else:
                    for i, doc in enumerate(results):
                        serial = _doc_to_dict(doc)
                        with st.expander(f"📄 {serial.get('_id', i)}", expanded=(i < 2)):
                            st.json(serial)

                    # JSON download
                    json_export = json.dumps([_doc_to_dict(d) for d in results], indent=2)
                    st.download_button(
                        "⬇ Download JSON",
                        data=json_export,
                        file_name=f"{selected_collection}_query_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        key="download_json_btn"
                    )

        # ══════════════════════════════════════════════════════════════════════
        # TAB 3: INSERT
        # ══════════════════════════════════════════════════════════════════════
        with tab_insert:
            st.subheader("➕ Insert Document")
            st.caption("Paste a valid JSON object to insert into the collection")

            insert_mode = st.radio("Insert mode", ["Single document", "Multiple documents (JSON array)"],
                                   horizontal=True, key="insert_mode")

            template_doc = {}
            if selected_collection == "history":
                template_doc = {
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "details": {"source": "Delhi", "destination": "Mumbai", "weight": "5.0", "priority": "Medium"},
                    "user_id": 1,
                    "user_name": "Test User",
                    "agent_output": "Sample agent output",
                    "status": "Booked"
                }

            insert_json = st.text_area(
                "Document JSON",
                value=json.dumps(template_doc if template_doc else {"field": "value"}, indent=2),
                height=250,
                key="insert_doc_json"
            )

            if st.button("➕ Insert Document(s)", key="insert_doc_btn", type="primary", use_container_width=True):
                try:
                    doc_data = json.loads(insert_json)
                    if insert_mode.startswith("Multiple"):
                        if not isinstance(doc_data, list):
                            st.error("❌ Expected a JSON array `[...]` for multiple documents.")
                        else:
                            # Convert timestamp strings to datetime for history collection
                            result = coll.insert_many(doc_data)
                            st.success(f"✅ Inserted **{len(result.inserted_ids)}** document(s)")
                            st.balloons()
                    else:
                        if isinstance(doc_data, list):
                            st.error("❌ Expected a single JSON object `{{...}}`, not an array.")
                        else:
                            result = coll.insert_one(doc_data)
                            st.success(f"✅ Inserted document with ID: `{result.inserted_id}`")
                            st.balloons()
                except json.JSONDecodeError as je:
                    st.error(f"❌ Invalid JSON: {je}")
                except Exception as e:
                    st.error(f"❌ Insert failed: {e}")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 4: DELETE
        # ══════════════════════════════════════════════════════════════════════
        with tab_delete:
            st.subheader("🗑️ Delete Documents")
            st.warning("⚠️ **Danger Zone** — Deleted documents cannot be recovered!")

            del_mode = st.radio("Delete mode", ["By Object ID", "By Filter Query"],
                                horizontal=True, key="del_mode_radio")

            if del_mode == "By Object ID":
                del_id = st.text_input("Document `_id` (ObjectId string)", key="del_by_id_input",
                                       placeholder="e.g. 507f1f77bcf86cd799439011")
                st.caption("⚡ Deletes exactly one document with this `_id`")

                if st.button("🗑️ Delete Document", key="del_by_id_btn", type="primary"):
                    if del_id.strip():
                        try:
                            oid = ObjectId(del_id.strip())
                            res = coll.delete_one({"_id": oid})
                            if res.deleted_count > 0:
                                st.success(f"✅ Deleted document `{del_id}`")
                                st.rerun()
                            else:
                                st.error("❌ No document found with that ID.")
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
                    else:
                        st.warning("Enter an Object ID.")

            else:  # By Filter Query
                del_filter_str = st.text_area(
                    "Delete filter (JSON)",
                    value='{"status": "Cancelled"}',
                    height=100,
                    key="del_filter_str",
                    help="All documents matching this filter will be deleted!"
                )
                del_one_only = st.checkbox("Delete only the FIRST match (safer)", value=True, key="del_one_only_chk")

                # Preview first
                col_preview, col_delete = st.columns(2)
                with col_preview:
                    if st.button("👁️ Preview matches", key="del_preview_btn"):
                        try:
                            filt = json.loads(del_filter_str)
                            matches = list(coll.find(filt).limit(5))
                            count   = coll.count_documents(filt)
                            st.info(f"Found **{count}** matching document(s). Showing up to 5:")
                            for m in matches:
                                st.json(_doc_to_dict(m))
                        except Exception as e:
                            st.error(f"Error: {e}")

                with col_delete:
                    confirm_del = st.text_input("Type **DELETE** to confirm", key="del_confirm_txt")
                    if st.button("🗑️ Delete Documents", key="del_filter_btn", type="primary"):
                        if confirm_del == "DELETE":
                            try:
                                filt = json.loads(del_filter_str)
                                if del_one_only:
                                    res = coll.delete_one(filt)
                                    st.success(f"✅ Deleted **{res.deleted_count}** document(s)")
                                else:
                                    res = coll.delete_many(filt)
                                    st.success(f"✅ Deleted **{res.deleted_count}** document(s)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
                        else:
                            st.error("Type DELETE to confirm the operation.")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 5: STATS
        # ══════════════════════════════════════════════════════════════════════
        with tab_stats:
            st.subheader(f"📈 Collection Stats — `{selected_collection}`")

            try:
                stats = db.command("collStats", selected_collection)
                db_stats = db.command("dbStats")

                # Collection stats
                cs1, cs2, cs3, cs4 = st.columns(4)
                cs1.metric("📄 Total Documents", stats.get("count", 0))
                cs2.metric("💾 Data Size", f"{round(stats.get('size', 0)/1024, 2)} KB")
                cs3.metric("🗜️ Storage Size", f"{round(stats.get('storageSize', 0)/1024, 2)} KB")
                cs4.metric("📝 Avg Doc Size", f"{round(stats.get('avgObjSize', 0), 0)} B")

                st.markdown("---")

                # Index info
                st.subheader("🔑 Indexes")
                try:
                    indexes = list(coll.list_indexes())
                    idx_rows = []
                    for idx in indexes:
                        idx_rows.append({
                            "Name": idx.get("name", ""),
                            "Key": str(dict(idx.get("key", {}))),
                            "Unique": idx.get("unique", False),
                            "Sparse": idx.get("sparse", False),
                        })
                    if idx_rows:
                        st.dataframe(pd.DataFrame(idx_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("No indexes found.")
                except Exception as ie:
                    st.warning(f"Could not fetch indexes: {ie}")

                # ── Create index ───────────────────────────────────────────────
                st.markdown("---")
                st.subheader("➕ Create Index")
                idx_col1, idx_col2, idx_col3 = st.columns(3)
                with idx_col1:
                    idx_field = st.text_input("Field name", placeholder="e.g. tracking_id", key="idx_field")
                with idx_col2:
                    idx_type = st.selectbox("Index type", ["Ascending (1)", "Descending (-1)", "Text"], key="idx_type")
                with idx_col3:
                    idx_unique = st.checkbox("Unique", key="idx_unique")

                if st.button("🔑 Create Index", key="create_idx_btn"):
                    if idx_field:
                        try:
                            if idx_type.startswith("Ascending"):
                                direction = 1
                            elif idx_type.startswith("Descending"):
                                direction = -1
                            else:
                                direction = "text"
                            coll.create_index([(idx_field, direction)], unique=idx_unique)
                            st.success(f"✅ Index created on `{idx_field}`")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.warning("Enter a field name.")

                st.markdown("---")

                # DB-level stats
                st.subheader("🗄️ Database Overview")
                d1, d2, d3 = st.columns(3)
                d1.metric("📚 Collections", db_stats.get("collections", 0))
                d2.metric("💾 DB Size", f"{round(db_stats.get('dataSize', 0)/1024/1024, 3)} MB")
                d3.metric("🗜️ Storage", f"{round(db_stats.get('storageSize', 0)/1024/1024, 3)} MB")

                # All collections summary table
                st.subheader("📋 All Collections Summary")
                try:
                    all_colls = db.list_collection_names()
                    coll_summary = []
                    for cn in all_colls:
                        try:
                            cs = db.command("collStats", cn)
                            coll_summary.append({
                                "Collection": cn,
                                "Documents": cs.get("count", 0),
                                "Data Size (KB)": round(cs.get("size", 0) / 1024, 2),
                                "Avg Doc (B)": round(cs.get("avgObjSize", 0), 0),
                                "Indexes": cs.get("nindexes", 0),
                            })
                        except Exception:
                            coll_summary.append({"Collection": cn, "Documents": "?", "Data Size (KB)": "?", "Avg Doc (B)": "?", "Indexes": "?"})

                    if coll_summary:
                        st.dataframe(pd.DataFrame(coll_summary), use_container_width=True, hide_index=True)
                except Exception as e:
                    st.warning(f"Could not load summary: {e}")

            except Exception as e:
                st.error(f"Could not fetch collection stats: {e}")
                st.info("This usually happens if the collection is empty or the user lacks admin privileges.")
