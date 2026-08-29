"""prompt 模板加载与渲染测试。"""

from django.test import SimpleTestCase

from apps.ai.prompts.loader import load_prompt, render_prompt


class PromptLoaderTests(SimpleTestCase):
    """提示词模板加载与渲染。"""

    def test_load_prompt_reads_file(self) -> None:
        """可按名加载 rag_system 模板。"""
        content = load_prompt("rag_system")
        self.assertIn("康复知识库", content)
        self.assertIn("{knowledge_chunks}", content)

    def test_load_prompt_accepts_txt_suffix(self) -> None:
        """带与不带 .txt 后缀结果一致。"""
        self.assertEqual(load_prompt("rag_system"), load_prompt("rag_system.txt"))

    def test_render_prompt_injects_placeholders(self) -> None:
        """render_prompt 注入动态内容且无残留占位符。"""
        out = render_prompt(
            "rag_system",
            therapist_name="张康复师",
            customer_name="李四",
            knowledge_chunks="术后 4 周可进行等长收缩训练。",
            question="膝盖术后能深蹲吗？",
        )
        self.assertIn("张康复师", out)
        self.assertIn("李四", out)
        self.assertIn("术后 4 周可进行等长收缩训练", out)
        self.assertIn("膝盖术后能深蹲吗", out)
        self.assertNotIn("{knowledge_chunks}", out)

    def test_load_missing_prompt_raises(self) -> None:
        """加载不存在的模板抛出 FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            load_prompt("no_such_prompt_xyz")
