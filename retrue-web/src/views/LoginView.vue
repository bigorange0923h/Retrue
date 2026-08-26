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
        <span class="brand-dot" />
        <span class="brand-name">Retrue</span>
      </div>
      <p class="login-subtitle">运动康复智能工作台</p>

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
  background: #f5f6f7;
}

.login-card {
  width: 380px;
  padding: 8px 12px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
}

.brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 4px;
  background: #07a358;
}

.brand-name {
  font-size: 22px;
  font-weight: 600;
}

.login-subtitle {
  text-align: center;
  color: #888;
  margin: 8px 0 24px;
}

.login-btn {
  width: 100%;
}
</style>
