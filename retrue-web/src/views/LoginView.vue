<script setup lang="ts">
/** 登录页。 */

import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push({ name: 'dashboard' })
  } catch {
    // 错误提示已由 Axios 拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-brand">
        <span class="brand-logo">R</span>
        <div class="brand-text">
          <span class="brand-name">Retrue</span>
          <span class="brand-sub">运动康复智能工作台</span>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @keyup.enter="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="handleSubmit">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 20% 20%, #e6f7ef 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, #f0ecfb 0%, transparent 50%),
    var(--retrue-bg);
}

.login-card {
  width: 400px;
  border-radius: var(--retrue-radius-lg);
  box-shadow: var(--retrue-shadow);
  border: 1px solid var(--retrue-border);
  padding: 36px 32px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  justify-content: center;
  margin-bottom: 28px;
}

.brand-logo {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--retrue-primary), var(--retrue-primary-dark));
  color: #fff;
  font-size: 24px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 16px rgb(7 163 88 / 30%);
}

.brand-text {
  display: flex;
  flex-direction: column;
  text-align: left;
}

.brand-name {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.brand-sub {
  font-size: 13px;
  color: var(--retrue-text-secondary);
  margin-top: 2px;
}

.login-btn {
  width: 100%;
  height: 40px;
  font-weight: 600;
}
</style>
