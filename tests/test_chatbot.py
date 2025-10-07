 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a//dev/null b/tests/test_chatbot.py
index 0000000000000000000000000000000000000000..314e0a704d8541ab7716987b6ebcd435700b7a46 100644
--- a//dev/null
+++ b/tests/test_chatbot.py
@@ -0,0 +1,27 @@
+import asyncio
+
+from app import ChatbotMessage, ChatbotReply, chatbot_endpoint, generate_chatbot_reply
+
+
+def test_chatbot_endpoint_classifies_gas_leak():
+    payload = ChatbotMessage(message="There is a strong gas leak in the kitchen")
+    response: ChatbotReply = asyncio.run(chatbot_endpoint(payload))
+    assert response.severity == "High"
+    assert response.category == "Gas/CO"
+    assert any("gas" in action.lower() for action in response.suggestedActions)
+
+
+def test_chatbot_greeting_reply():
+    reply, severity, category, actions = generate_chatbot_reply("Hello there")
+    assert "hello" in reply.lower()
+    assert severity == "Low"
+    assert category == "Other"
+    assert actions == ["Share details about the issue"]
+
+
+def test_chatbot_endpoint_handles_unknown_issue():
+    payload = ChatbotMessage(message="My window is squeaking")
+    response: ChatbotReply = asyncio.run(chatbot_endpoint(payload))
+    assert response.category == "Other"
+    assert response.severity == "Low"
+    assert response.suggestedActions
 
EOF
)
