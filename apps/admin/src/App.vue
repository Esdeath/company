<template>
  <div class="admin-shell">
    <header class="masthead">
      <div class="identity" aria-label="企业研究资料库管理端">
        <span class="identity__library">企业研究资料库</span>
        <span class="identity__division">管理端</span>
      </div>

      <p class="archive-mark" aria-label="里程碑 01，待校勘">
        <span>里程碑 01</span>
        <strong>待校勘</strong>
      </p>
    </header>

    <main>
      <section class="intro" aria-labelledby="page-title">
        <p class="eyebrow">管理端工程骨架</p>
        <h1 id="page-title">资料管理后台</h1>
        <p class="intro__summary">
          当前里程碑只建立独立、可验证的管理端入口。登录与资料上传将在后续里程碑实现。
        </p>
      </section>

      <section class="roadmap" aria-labelledby="roadmap-title">
        <div class="section-heading">
          <p>后续能力清单</p>
          <h2 id="roadmap-title">边界先于功能</h2>
        </div>

        <ul class="roadmap-list">
          <li>
            <span class="roadmap-list__label">权限</span>
            <div>
              <h3>内部身份验证</h3>
              <p>后续接入登录与访问控制；此页面不提供可误用的临时入口。</p>
            </div>
          </li>
          <li>
            <span class="roadmap-list__label">资料</span>
            <div>
              <h3>资料整理与归档</h3>
              <p>后续承载上传、校勘与发布流程；当前不展示占位控件或样例数据。</p>
            </div>
          </li>
        </ul>
      </section>

      <nav class="public-return" aria-label="站点入口">
        <a href="/">
          <span aria-hidden="true">←</span>
          返回公开端
        </a>
        <p>公开阅读与内部管理保持分离</p>
      </nav>
    </main>

    <footer class="footer">
      <p>企业研究资料库 · 内部资料边界</p>
      <p>当前版本不处理登录或上传</p>
    </footer>
  </div>
</template>
