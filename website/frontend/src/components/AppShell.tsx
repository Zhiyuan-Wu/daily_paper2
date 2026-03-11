import {
  FileSearchOutlined,
  MenuFoldOutlined,
  SettingOutlined,
  SolutionOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Grid, Layout, Menu, Space, Typography } from 'antd';
import type { MenuProps } from 'antd';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useUIStore } from '../store/uiStore';

const { Header, Sider, Content } = Layout;

const MENU_ITEMS: MenuProps['items'] = [
  {
    key: '/daily-report',
    icon: <SolutionOutlined />,
    label: '论文日报',
  },
  {
    key: '/paper-explore',
    icon: <FileSearchOutlined />,
    label: '论文探索',
  },
  {
    key: '/settings',
    icon: <SettingOutlined />,
    label: '设置',
  },
];

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.lg;

  const drawerOpen = useUIStore((state) => state.drawerOpen);
  const setDrawerOpen = useUIStore((state) => state.setDrawerOpen);

  const selectedKeys = useMemo(() => {
    const path = location.pathname;
    if (path.startsWith('/paper-explore')) {
      return ['/paper-explore'];
    }
    if (path.startsWith('/settings')) {
      return ['/settings'];
    }
    return ['/daily-report'];
  }, [location.pathname]);

  const menu = (
    <Menu
      mode="inline"
      items={MENU_ITEMS}
      selectedKeys={selectedKeys}
      onClick={(event) => {
        navigate(event.key);
        setDrawerOpen(false);
      }}
      style={{ borderInlineEnd: 0, background: 'transparent' }}
    />
  );

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {isMobile ? (
        <Header className="app-header mobile-header">
          <Space size={12}>
            <Button
              aria-label="Open menu"
              icon={<MenuFoldOutlined />}
              onClick={() => setDrawerOpen(true)}
            />
            <Typography.Title level={4} style={{ margin: 0 }}>
              Daily Paper
            </Typography.Title>
          </Space>
          <Drawer
            title="导航"
            placement="left"
            width={260}
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            styles={{ body: { padding: 0 } }}
          >
            <div className="side-brand">Daily Paper</div>
            {menu}
          </Drawer>
        </Header>
      ) : (
        <Sider width={240} className="app-sider" theme="light">
          <div className="side-brand">Daily Paper</div>
          {menu}
        </Sider>
      )}

      <Layout>
        {!isMobile ? <Header className="app-header desktop-header" /> : null}
        <Content className="app-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
