// SPDX-License-Identifier: MIT
import { test, expect } from '@playwright/test';

const email = `e2e-${Date.now()}@test.local`;
const password = 'e2e-test-password-secure-01';
const name = 'Usuário E2E';

test.describe('Autenticação', () => {
  test('registro, login e logout', async ({ page }) => {
    await page.goto('/');

    // Deve exibir formulário de login
    await expect(page.getByRole('heading', { name: 'Entrar no workspace' })).toBeVisible();

    // Alterna para registro
    await page.getByRole('button', { name: 'Criar uma conta' }).click();
    await expect(page.getByRole('heading', { name: 'Criar sua conta' })).toBeVisible();

    // Preenche e envia o formulário de registro
    await page.getByLabel('Nome').fill(name);
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Senha').fill(password);
    await page.getByRole('button', { name: 'Criar conta' }).click();

    // Após registro deve aparecer o workspace
    await expect(page.getByText('Dashboard')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(name)).toBeVisible();

    // Logout
    await page.getByRole('button', { name: /Sair/ }).click();

    // Volta ao formulário de login
    await expect(page.getByRole('heading', { name: 'Entrar no workspace' })).toBeVisible();

    // Login com as credenciais criadas
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Senha').fill(password);
    await page.getByRole('button', { name: 'Entrar' }).click();

    // Workspace carregado novamente
    await expect(page.getByText('Dashboard')).toBeVisible({ timeout: 20000 });
  });

  test('senha incorreta exibe erro', async ({ page }) => {
    await page.goto('/');
    await page.getByLabel('Email').fill('inexistente@test.local');
    await page.getByLabel('Senha').fill('senha-errada-qualquer');
    await page.getByRole('button', { name: 'Entrar' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
  });
});
