export default defineAppConfig({
  pages: ['pages/index/index'],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'AI驻车露营情报助手',
    navigationBarTextStyle: 'black'
  },
  // spec-013 D1：微信小程序定位权限声明。调 wx.getLocation 前必须声明
  // scope.userLocation + requiredPrivateInfos，否则定位无法正常工作。
  // 这两项是 weapp-only 配置，H5 构建忽略。
  permission: {
    'scope.userLocation': {
      desc: '用于在地图上显示你附近的露营/驻车点位'
    }
  },
  requiredPrivateInfos: ['getLocation']
})
